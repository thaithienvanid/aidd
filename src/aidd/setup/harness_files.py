"""The team's files in each coding agent's own format: one renderer per harness, looked up by its key.

`team_install` reads a role or a flow command once, from the aidd-team source, and hands it here. A role becomes a
`Role`, which each harness in AGENT_FILES writes as its agent file. A flow command becomes a file through FLOW_FILES,
for the harnesses that have commands of their own. EXTRA_FILES holds a harness's other files, such as Antigravity's
`.agents/skills.json`. The words inside each file are `harness_text`'s.

To support another harness's agents: add its renderer to AGENT_FILES (and a `Voice` in `harness_text.VOICES`); for
its commands, add a `Flow` to FLOW_FILES. `team_install`, `aidd uninstall`, and the tests read these tables, so nothing
else changes. Each renderer cites the format it follows.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable

from aidd.setup import harness_text


@dataclasses.dataclass(frozen=True)
class Role:
    """One aidd-team role, ready to write: its Claude Code tools say what it may do, and `model` is the harness's own
    value for the configured model (None: the harness's default), with `note` saying why when it cannot run it."""

    name: str
    description: str
    prompt: str
    tools: frozenset[str]
    model: str | None = None
    note: str | None = None

    @property
    def writes(self) -> bool:
        return bool(self.tools & {"Write", "Edit"})

    @property
    def shell(self) -> bool:
        return "Bash" in self.tools

    @property
    def web(self) -> bool:
        return bool(self.tools & {"WebFetch", "WebSearch"})

    @property
    def starts_helpers(self) -> bool:
        return any(t.startswith("Agent(") for t in self.tools)

    def yaml_model(self) -> str:
        """The model lines of a YAML front matter: the `model:` field, or a comment saying why there is none."""
        return (f"model: {self.model}\n" if self.model else "") + (f"# {self.note}\n" if self.note else "")


def _codex(role: Role) -> tuple[str, str]:
    """`.codex/agents/<name>.toml`: name, description, developer_instructions, and `model`."""
    lines = [f"name = {json.dumps(role.name)}", f"description = {json.dumps(role.description)}"]
    if role.model:
        lines.append(f"model = {json.dumps(role.model)}")
    if role.note:
        lines.append(f"# {role.note}")
    if not role.writes:  # a read-only role may run commands (git diff, the tests); the sandbox still keeps its writes out
        lines.append('sandbox_mode = "read-only"')
    lines.append(f"developer_instructions = {json.dumps(role.prompt, ensure_ascii=False)}")
    return f".codex/agents/{role.name}.toml", "\n".join(lines) + "\n"


def _copilot(role: Role) -> tuple[str, str]:
    """`.github/agents/<name>.agent.md`: YAML front matter (description required); the body is the prompt."""
    front = f"name: {role.name}\ndescription: {json.dumps(role.description)}\n{role.yaml_model()}"
    return f".github/agents/{role.name}.agent.md", f"---\n{front}---\n\n{role.prompt}"


def _antigravity(role: Role) -> tuple[str, str]:
    """`.agents/agents/<name>.md`: a subagent only (never the main agent), with the Antigravity tools its Claude Code
    tools match (the agent front matter `agy` 1.3 reads: `subagent`, `mainAgent`, `model`, `tools`)."""
    tools = ["view_file", "grep_search", "find_by_name"]
    tools += ["write_to_file", "replace_file_content", "multi_replace_file_content"] if role.writes else []
    tools += ["run_command"] if role.shell else []
    tools += ["search_web", "read_url_content"] if role.web else []
    tools += ["invoke_subagent"] if role.starts_helpers else []
    listed = "tools:\n" + "".join(f"  - {t}\n" for t in tools)
    front = f"name: {role.name}\ndescription: {json.dumps(role.description)}\nsubagent: true\nmainAgent: false\n{role.yaml_model()}{listed}"
    return f".agents/agents/{role.name}.md", f"---\n{front}---\n\n{role.prompt}"


def _opencode(role: Role) -> tuple[str, str]:
    """`.opencode/agents/<name>.md`: description, mode, model, permissions; the file name is the agent name.

    aidd writes OpenCode's native V2 format, a `permissions:` rule list (action/resource/effect); V2 still loads the V1
    format (`permission`, `tools`, `prompt`). OpenCode V1 ignores these rules, so on V1 the roles run without them. A
    role that writes may edit and is asked before each shell command; one without a write area is denied edits and
    still asked before a command."""
    perms = (
        f'permissions:\n  - action: edit\n    resource: "*"\n    effect: {"allow" if role.writes else "deny"}\n'
        f'  - action: shell\n    resource: "*"\n    effect: {"ask" if role.shell else "deny"}\n'
    )
    front = f"description: {json.dumps(role.description)}\nmode: subagent\n{role.yaml_model()}{perms}"
    return f".opencode/agents/{role.name}.md", f"---\n{front}---\n\n{role.prompt}"


def _grok(role: Role) -> tuple[str, str]:
    """`.grok/agents/<name>.md`: YAML front matter and one `tools:` line of Grok Build's tool names (the agent file
    Grok reads). No role lists `spawn_subagent`: a role file is depth 1, and the lead is the one that starts a role.
    `model:` is a bare id when the configured model is xAI's."""
    tools = ["read_file", "grep", "list_dir", "run_terminal_command", "web_search", "web_fetch"]
    if role.writes:
        tools += ["search_replace", "write"]
    front = f"name: {role.name}\ndescription: {json.dumps(role.description)}\n{role.yaml_model()}tools: {', '.join(tools)}\n"
    return f".grok/agents/{role.name}.md", f"---\n{front}---\n\n{role.prompt}"


def _kiro(role: Role) -> tuple[str, str]:
    """`.kiro/agents/<name>.json`: name, description, prompt, tools, and `model`."""
    tools = ["read"] + (["write"] if role.writes else []) + (["shell"] if role.shell else [])
    data: dict = {"name": role.name, "description": role.description, "prompt": role.prompt, "tools": tools}
    if role.model:
        data["model"] = role.model
    return f".kiro/agents/{role.name}.json", json.dumps(data, indent=2, ensure_ascii=False) + "\n"


# Each harness's agent file for a role, in the format its documentation gives (checked 2026-09-28; Antigravity and
# Grok Build 2026-10-16).
AGENT_FILES: dict[str, Callable[[Role], tuple[str, str]]] = {
    "codex": _codex,
    "copilot": _copilot,
    "antigravity": _antigravity,
    "opencode": _opencode,
    "kiro": _kiro,
    "grok-build": _grok,
}


@dataclasses.dataclass(frozen=True)
class Flow:
    """How a harness holds a flow command: its path for a flow name (`aidd-implement`), and its text from the source
    file's name (`implement.md`), the flow name, the description, and the shared body. `extra` gives the other files
    one flow needs there, by path."""

    path: Callable[[str], str]
    render: Callable[[str, str, str, str], str]
    extra: Callable[[str], dict[str, str]] | None = None


def _opencode_command(source: str, flow: str, description: str, body: str) -> str:
    """An OpenCode V2 command: front matter with only `description` (OpenCode reads no Claude Code
    `disable-model-invocation` or `argument-hint`), and the body with OpenCode's words (`harness_text`)."""
    return f"---\ndescription: {json.dumps(description)}\n---\n\n{harness_text.command(source, body)}"


def _antigravity_skill(source: str, flow: str, description: str, body: str) -> str:
    """A Google Antigravity skill, which a person runs as `/<flow>`: Antigravity deprecates workflows
    (`.agents/workflows/`) for skills, which take the same slash command. The front matter is the skill's `name` and
    `description`; the body names what `$ARGUMENTS` stands for, since no Antigravity documentation says a skill's text
    is expanded."""
    lead = f"`$ARGUMENTS` below stands for what the person typed after `/{flow}`."
    return f"---\nname: {flow}\ndescription: {json.dumps(description)}\n---\n\n{lead}\n\n{harness_text.command(source, body, 'antigravity')}"


def _grok_skill(source: str, flow: str, description: str, body: str) -> str:
    """A Grok Build skill under `.grok/skills/<flow>/SKILL.md`, which a person runs as `/<flow>`: Grok lists a skill as
    a slash command only with `user-invocable: true`, and expands `$ARGUMENTS` in its text itself (grok 1.0.60's guide).
    The body uses Grok's words (`harness_text`)."""
    front = f"name: {flow}\ndescription: {json.dumps(description)}\nuser-invocable: true\n"
    return f"---\n{front}---\n\n{harness_text.command(source, body, 'grok-build')}"


# Codex and Antigravity read the same folder of skills, so where both are wired, one voice serves both.
SHARED_SKILLS = "agents-skills"
SHARED_FLOWS = {SHARED_SKILLS: ("antigravity", "codex")}


def _codex_skill(source: str, flow: str, description: str, body: str, voice: str = "codex") -> str:
    """A Codex skill under `.agents/skills/<flow>/SKILL.md`, the one project folder Codex reads skills from (codex 0.156):
    front matter with `name` and `description`, which Codex requires, and the body in Codex's words (`harness_text`).
    A person runs it as `$<flow>`; `agents/openai.yaml` beside it keeps Codex from starting it on its own, as Claude
    Code's commands set `disable-model-invocation`."""
    lead = f"`$ARGUMENTS` below stands for what the person typed after `${flow}`."
    if voice == SHARED_SKILLS:
        lead = f"`$ARGUMENTS` below stands for what the person typed after `/{flow}` in Antigravity, or `${flow}` in Codex."
    return f"---\nname: {flow}\ndescription: {json.dumps(description)}\n---\n\n{lead}\n\n{harness_text.command(source, body, voice)}"


def _shared_skill(source: str, flow: str, description: str, body: str) -> str:
    return _codex_skill(source, flow, description, body, SHARED_SKILLS)


def _codex_policy(flow: str) -> dict[str, str]:
    """Codex's skill metadata (`agents/openai.yaml`): a flow runs only when a person names it."""
    return {f".agents/skills/{flow}/agents/openai.yaml": "policy:\n  allow_implicit_invocation: false\n"}


# The harnesses with commands of their own, and how each holds a flow; a SHARED_FLOWS key stands for its harnesses.
FLOW_FILES: dict[str, Flow] = {
    "antigravity": Flow(lambda flow: f".agents/skills/{flow}/SKILL.md", _antigravity_skill),
    "opencode": Flow(lambda flow: f".opencode/commands/{flow}.md", _opencode_command),
    "grok-build": Flow(lambda flow: f".grok/skills/{flow}/SKILL.md", _grok_skill),
    "codex": Flow(lambda flow: f".agents/skills/{flow}/SKILL.md", _codex_skill, _codex_policy),
    SHARED_SKILLS: Flow(lambda flow: f".agents/skills/{flow}/SKILL.md", _shared_skill, _codex_policy),
}


def flow_kinds(harnesses: list[str]) -> list[str]:
    """The FLOW_FILES keys whose files `harnesses` get: each harness's own, or the shared one where all its harnesses are."""
    kinds = [h for h in FLOW_FILES if h in harnesses]
    for shared, members in SHARED_FLOWS.items():
        if all(m in kinds for m in members):
            kinds = [k for k in kinds if k not in members] + [shared]
    return kinds


def _antigravity_extras(claude_files: bool) -> dict[str, str]:
    """`.agents/skills.json` naming `.claude/skills/`, where the practice skills and domain packs are, for Antigravity to
    discover too (its JSON configuration guide: workspace-relative `entries`)."""
    return {".agents/skills.json": json.dumps({"entries": [{"path": ".claude/skills"}]}, indent=2) + "\n"} if claude_files else {}


# A harness's other files, given whether the team's Claude Code files (`.claude/`) are written too.
EXTRA_FILES: dict[str, Callable[[bool], dict[str, str]]] = {"antigravity": _antigravity_extras}
