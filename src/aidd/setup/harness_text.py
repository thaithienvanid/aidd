"""The team's role and command files as each coding agent other than Claude Code reads them.

The roles and the flow commands are written once, for Claude Code, and a few of their words name what only Claude Code
has: its `Skill`, `Agent`, `Edit`, and `Write` tools, the skills an agent file preloads, its session variable, `/clear`
and `/loop`, and its tier names. Each harness that gets role files
(`team_install.NATIVE_AGENT_HARNESSES`) has a `Voice` here: how its agents find a skill, what its agent file enforces,
and whether the role can start a subagent, each from the harness's own documentation. `agent()` swaps every Claude Code
phrase (`AGENT`) for that harness's words. Where a capability could not be verified, the voice says less: it tells the
role what to do and promises no enforcement.

OpenCode v2, Google Antigravity, Grok Build, and Codex also get the flow commands; `CODEX_LEAD` and `CODEX_COMMANDS` are
Codex's, and `SHARED_SKILLS_LEAD` is the one `.agents/skills/` file Antigravity and Codex share where both are wired. `command()` and `lead_block()` take the harness;
`ANTIGRAVITY_LEAD` and `ANTIGRAVITY_COMMANDS` are Antigravity's, `GROK_LEAD` and `GROK_COMMANDS` are Grok Build's, and `LEAD` and
`COMMANDS` are OpenCode's (checked against https://opencode.ai/v2/docs on 2026-10-12): the `subagent`, `skill`, `edit`,
and `write` tools, and the `explore` subagent.

Each swap names the exact text it replaces, so a reworded source shows up as a swap that no longer matches
(`tests/test_harness_text.py`, `tests/test_opencode.py`), never as Claude Code wording left in another harness's file.
"""

from __future__ import annotations

import dataclasses
import re

from aidd import knowledge

# The first paragraph of a role file in a harness where no aidd hook runs.
ADVISORY = (
    "No hook checks this role's writes: follow the write area, the risk rules (`aidd risk`), and the loop contract below "
    "yourself, and on an ask hand the question to the lead, who asks the person."
)

# Every Claude Code phrase of a role agent that names what only Claude Code has, by the `Voice` field that replaces it. The
# swaps apply in this order, as do the swaps of `LEAD` and of each `COMMANDS` list.
AGENT = {
    "rulebook": "The aidd skill (`aidd:aidd`; load it with `Skill` for a rule not here) is the rulebook.",
    "rulebook_preloaded": "The aidd skill, preloaded, is the rulebook.",
    "mcp": "Prefer the `aidd` MCP tools.",
    "read_only": "You write no file, with a tool or the shell.",
    "edit": "with one Edit (Write only a new or mostly rewritten file)",
    "helpers": "split large, independent work across subagents of your own `aidd-<role>` type, or helpers, which only read. Give each the practice skill for its work.",
}

# aidd wires its MCP server only for Claude Code (`config.harnesses`), so elsewhere the tools are there only if a person added them.
MCP = "Prefer the `aidd` MCP tools when this agent has them, else the `aidd` command."
REFUSAL = "or a refused tool call."
EDIT = "with one targeted edit (rewrite a whole file only when it is new or mostly rewritten)"
READ_SKILL = "The aidd skill (`.agents/skills/aidd/SKILL.md`; read it for a rule not here) is the rulebook."


@dataclasses.dataclass(frozen=True)
class Voice:
    """How one harness's role files word what Claude Code's word with its own tools and hook."""

    skills: str  # how this harness finds a skill, after the advisory
    rulebook: str = READ_SKILL
    read_only: str = "You write no file, not even through the shell."
    refusal: str = REFUSAL
    edit: str = EDIT
    helpers: str | None = None  # None keeps Claude Code's sentence: the role can start a subagent here too
    advisory: str = ADVISORY

    def swaps(self) -> list[tuple[str, str]]:
        """(Claude Code text, this harness's text) for each phrase in `AGENT`."""
        new = {"rulebook": self.rulebook, "rulebook_preloaded": self.rulebook, "mcp": MCP, "read_only": self.read_only}
        new |= {"edit": self.edit, "helpers": self.helpers or AGENT["helpers"]}
        return [(AGENT[k], new[k]) for k in AGENT]


VOICES: dict[str, Voice] = {
    # A role's file for any harness that reads `.agents/skills/` but has no agent file of aidd's: no harness's tool named.
    "agents-skills": Voice(
        skills=(
            "Read an `aidd-<name>` practice skill or domain pack from `.agents/skills/` or `.claude/skills/` when your harness does not load it by itself."
        ),
    ),
    # https://learn.chatgpt.com/docs/build-skills: Codex scans `.agents/skills` from the working directory up to the
    # repository root, and selects a skill "when your task aligns with the skill's description field".
    # https://learn.chatgpt.com/docs/agent-configuration/subagents: a custom agent may set `sandbox_mode`, and local
    # Codex "spawn[s] agents after a direct request or applicable project or skill instruction".
    # https://learn.chatgpt.com/docs/sandboxing: in read-only, the agent "can't edit files or run commands without approval".
    "codex": Voice(
        skills=(
            "Codex looks for skills only in `.agents/skills/`, so read an `aidd-<name>` practice skill or domain pack "
            "yourself, from `.claude/skills/aidd-<name>/SKILL.md` when the team is installed there."
        ),
        read_only=(
            "You write no file, not even through the shell: this file runs you in Codex's read-only sandbox, where an "
            "edit or a command needs a person's approval."
        ),
    ),
    # https://docs.github.com/en/copilot/concepts/agents/about-agent-skills: project skills live in `.github/skills`,
    # `.claude/skills`, or `.agents/skills`, and Copilot "can load [them] when relevant".
    # https://docs.github.com/en/copilot/reference/custom-agents-configuration: `tools`, "If unset, defaults to all
    # tools" (aidd sets none, so nothing here enforces a read-only role), and the `agent` tool invokes another custom agent.
    "copilot": Voice(
        skills=(
            "Copilot loads a skill from `.agents/skills/` or `.claude/skills/` when it is relevant to the task; read a "
            "skill's `SKILL.md` yourself when you need it now."
        ),
    ),
    # Antigravity's customization guide (shipped in `agy` 1.3): a Markdown agent in `.agents/agents/` lists its `tools`,
    # skills load from `.agents/skills/` and the directories `.agents/skills.json` names (init names `.claude/skills/`),
    # and only a skill's name and description sit in the context until the agent activates it.
    "antigravity": Voice(
        skills=(
            "Antigravity lists the workspace's skills, the `aidd-<name>` practice skills and domain packs among them "
            "when `.agents/skills.json` names `.claude/skills/`; activate one when its description fits your task, or "
            "read its `SKILL.md` yourself."
        ),
        read_only=(
            "You write no file, not even through the shell. This file gives you no `write` tool (no `write_file`, "
            "`edit_file`, `write_to_file`, or `replace_file_content`), but `shell` can still write through "
            "`run_command`, so don't."
        ),
        edit="with one `edit_file` or `replace_file_content` (`write_file` or `write_to_file` only for a new or mostly rewritten file)",
    ),
    # https://kiro.dev/docs/custom-agents/configuration-reference/: `tools` is "the tools available to the agent"
    # (`read`, `write`, `shell`), and an agent reaches a skill through a `skill://` entry in its `resources`. aidd's
    # agent file lists no resources and no tool that starts another agent.
    "kiro": Voice(
        skills=(
            "This agent file attaches no skill, so read the `SKILL.md` of each one you need: an `aidd-<name>` practice "
            "skill or domain pack is in `.claude/skills/aidd-<name>/` when the team is installed there."
        ),
        # The file grants `shell` to a role that reads with one (git diff, the tests), and `shell` can write, so the
        # text claims only the missing `write` tool and leaves the shell to the role.
        read_only="You write no file, not even through the shell. This file gives you no `write` tool, but `shell` can still write, so don't.",
        helpers="split large, independent work into parts and take them one at a time, since this file gives you no tool that starts a subagent.",
    ),
    # https://opencode.ai/v2/docs/skills: OpenCode finds skills in `.opencode/skills/`, `.claude/skills/`, and
    # `.agents/skills/`, and an agent loads one with the `skill` tool. https://opencode.ai/v2/docs/agents: the agent's
    # `permissions:` rules are enforced on its edits and shell commands.
    "opencode": Voice(
        skills="Load a skill, the aidd skill or an `aidd-<name>` practice skill or domain pack, with the `skill` tool.",
        rulebook="The aidd skill (`aidd`; load it with the `skill` tool for a rule not here) is the rulebook.",
        refusal="or a denied permission.",
        edit="with one `edit` (`write` only a new or mostly rewritten file)",
    ),
    # Grok Build reads `.grok/agents/*.md` (one `tools:` line) and loads skills from `.grok/skills/` and `.agents/skills/`.
    # No role file lists `spawn_subagent`: Grok's subagent depth is 1, so the lead starts every role.
    "grok-build": Voice(
        skills=(
            "Grok Build loads a skill from `.grok/skills/` or `.agents/skills/` when its description fits the task; read "
            "its `SKILL.md` yourself when you need it now. The `aidd-<name>` practice skills and domain packs are in "
            "`.claude/skills/aidd-<name>/` when the team is installed there."
        ),
        read_only=(
            "You write no file, not even through the shell. This file gives you no `write` tool (no `search_replace` or "
            "`write`), but `shell` can still write through `run_terminal_command`, so don't."
        ),
        edit="with one `search_replace` (`write` only a new or mostly rewritten file)",
        helpers="split large, independent work into parts and take them one at a time, since this file gives you no tool that starts a subagent.",
    ),
}


def agent(harness: str, body: str) -> str:
    """A role agent's prompt for `harness`: its advisory, how it finds skills, and the body with each swap of its voice.
    Codex runs a flow as `$aidd-<flow>`, so its role files name each flow that way."""
    voice = VOICES[harness]
    for old, new in voice.swaps():
        body = body.replace(old, new)
    body = _SLASH_FLOW.sub("$aidd-", body) if harness == "codex" else body
    return f"{voice.advisory} {voice.skills}\n\n{body}"


# A flow named as `/aidd-<flow>` in a file both Codex and Antigravity read (the shared flows, the roles reference), where
# Codex runs it as `$aidd-<flow>`.
_NAMED_FLOW = re.compile(r"`/aidd-([a-z][a-z-]*)`")


def both_flow_names(text: str) -> str:
    """`text` with each `/aidd-<flow>` also named the way Codex runs it: "`/aidd-fix` (`$aidd-fix` in Codex)"."""
    return _NAMED_FLOW.sub(lambda m: f"`/aidd-{m.group(1)}` (`$aidd-{m.group(1)}` in Codex)", text)


# The installed roles reference (`team_install.TEAM_ROLES_REF`), which every harness reads, names Claude Code's `Skill`
# tool; elsewhere a role loads a practice skill the way its own file says.
SHARED = [
    ("the practice skills it loads with `Skill`: at most", "the practice skills it loads: at most"),
    ("(`Skill`: at most two from the Task, plus the ones for its files)", "(at most two from the Task, plus the ones for its files)"),
]


def shared(text: str) -> str:
    """A file every harness reads, with `SHARED`'s swaps."""
    for old, new in SHARED:
        text = text.replace(old, new)
    return text


# OpenCode's flow commands. The lead's rules (`schemas/roles.json`, `loop.lead`) that name Claude Code's tools, as OpenCode words them.
LEAD = {
    "Pass the `model` in every Agent call: the alias the role's agent file names. If it names a full model id or `inherit`, pass none. "
    "Read-only search helpers (Explore) take an execution-tier role's alias.": (
        "Launch each role with the `subagent` tool. Its agent file names its model, so pass none. For read-only search, launch the `explore` subagent."
    ),
    "Start each command in a fresh session (or after `/clear`).": "Start each command in a fresh session.",
    "with one Edit (Write only a new or mostly rewritten file)": "with one `edit` (`write` only a new or mostly rewritten file)",
}

# Per command file: (Claude Code text, OpenCode text). Every pair must match its file once.
COMMANDS: dict[str, list[tuple[str, str]]] = {
    "autopilot.md": [
        (
            "Read the step's command file, `${CLAUDE_PLUGIN_ROOT}/commands/<flow>.md`, follow its steps",
            "Read the step's command file, `.opencode/commands/aidd-<flow>.md`, follow its steps",
        ),
        (
            'one Agent call per step with `isolation: "worktree"`, all in one message.',
            "create each worktree with `git worktree add`, then launch one subagent per step, all in one message, each told to work only in its worktree.",
        ),
        ("A person stops the run with Esc, or by telling you to stop.", "A person stops the run by telling you to stop."),
    ],
    "fix.md": [("skill with the Skill tool before your first edit", "skill before your first edit")],
    "implement.md": [
        ("skill with the Skill tool before your first edit", "skill before your first edit"),
        (
            'Make one Agent call per Task with `isolation: "worktree"`, all launched in one message. Each Task then builds '
            "in its own git worktree, on its own branch.",
            "Give each Task its own git worktree on its own branch (`git worktree add`), then launch one subagent per Task, "
            "all in one message, each told to work only in its worktree.",
        ),
    ],
    "mvp.md": [
        (
            'Make one Agent call per slice with `isolation: "worktree"`, all launched in one message.',
            "Create each worktree on its own branch (`git worktree add`), then launch one subagent per slice, all in one "
            "message, each told to work only in its worktree.",
        ),
    ],
    "propose.md": [("Tell the subagent to load that skill with `Skill`.", "Tell the subagent to load that skill.")],
    "specify.md": [("skill with the Skill tool before your first edit", "skill before your first edit")],
}

_LEAD_BLOCK = re.compile(r"<!-- aidd:gen roles:lead -->\n.*?<!-- aidd:end -->\n", re.S)

# Antigravity's flow commands, written as skills (`harness_files.FLOW_FILES`). The lead starts each role with the
# `invoke_subagent` tool, and a subagent's `share` workspace is its own worktree of the repository (the tool's schema,
# in `agy` 1.3).
ANTIGRAVITY_LEAD = {
    "Pass the `model` in every Agent call: the alias the role's agent file names. If it names a full model id or `inherit`, pass none. "
    "Read-only search helpers (Explore) take an execution-tier role's alias.": (
        "Launch each role with the `invoke_subagent` tool, naming its agent, such as `aidd-developer`. Its agent file "
        "names its tools, so pass no model unless the person asks for one."
    ),
    "Start each command in a fresh session (or after `/clear`).": "Start each command in a fresh conversation.",
    "with one Edit (Write only a new or mostly rewritten file)": (
        "with one `edit_file` or `replace_file_content` (`write_file` or `write_to_file` only for a new or mostly rewritten file)"
    ),
}

ANTIGRAVITY_COMMANDS: dict[str, list[tuple[str, str]]] = {
    **COMMANDS,
    "autopilot.md": [
        (
            "Read the step's command file, `${CLAUDE_PLUGIN_ROOT}/commands/<flow>.md`, follow its steps",
            "Read the step's command file, `.agents/skills/aidd-<flow>/SKILL.md`, follow its steps",
        ),
        (
            'one Agent call per step with `isolation: "worktree"`, all in one message.',
            "launch one subagent per step in a single `invoke_subagent` call, each in the `share` workspace mode.",
        ),
        ("A person stops the run with Esc, or by telling you to stop.", "A person stops the run by telling you to stop."),
    ],
    "implement.md": [
        ("skill with the Skill tool before your first edit", "skill before your first edit"),
        (
            'Make one Agent call per Task with `isolation: "worktree"`, all launched in one message. Each Task then builds '
            "in its own git worktree, on its own branch.",
            "Launch one subagent per Task in a single `invoke_subagent` call, each in the `share` workspace mode. Each "
            "Task then builds in its own git worktree, on its own branch.",
        ),
    ],
    "mvp.md": [
        (
            'Make one Agent call per slice with `isolation: "worktree"`, all launched in one message.',
            "Launch one subagent per slice in a single `invoke_subagent` call, each in the `share` workspace mode.",
        ),
    ],
}


# Grok Build's flow commands, written as skills. The lead starts each role with `spawn_subagent` and passes no model.
# A Task worktree is `git worktree add` (Grok has no `isolation:` flag).
GROK_LEAD = {
    "Pass the `model` in every Agent call: the alias the role's agent file names. If it names a full model id or `inherit`, pass none. "
    "Read-only search helpers (Explore) take an execution-tier role's alias.": (
        "Start each role with `spawn_subagent` and `subagent_type` `aidd-<role>`. Pass no model. Give a Task its own worktree with `git worktree add`."
    ),
    "Start each command in a fresh session (or after `/clear`).": "Start each command in a fresh session.",
    "with one Edit (Write only a new or mostly rewritten file)": "with one `search_replace` (`write` only a new or mostly rewritten file)",
}

GROK_COMMANDS: dict[str, list[tuple[str, str]]] = {
    **COMMANDS,
    "autopilot.md": [
        (
            "Read the step's command file, `${CLAUDE_PLUGIN_ROOT}/commands/<flow>.md`, follow its steps",
            "Read the step's command file, `.grok/skills/aidd-<flow>/SKILL.md`, follow its steps",
        ),
        (
            'one Agent call per step with `isolation: "worktree"`, all in one message.',
            "create each worktree with `git worktree add`, then launch one spawn_subagent per step, all in one message, each told to work only in its worktree.",
        ),
        ("A person stops the run with Esc, or by telling you to stop.", "A person stops the run by telling you to stop."),
    ],
    "implement.md": [
        ("skill with the Skill tool before your first edit", "skill before your first edit"),
        (
            'Make one Agent call per Task with `isolation: "worktree"`, all launched in one message. Each Task then builds '
            "in its own git worktree, on its own branch.",
            "Give each Task its own git worktree on its own branch (`git worktree add`), then launch one spawn_subagent per Task, "
            "all in one message, each told to work only in its worktree.",
        ),
    ],
    "mvp.md": [
        (
            'Make one Agent call per slice with `isolation: "worktree"`, all launched in one message.',
            "Give each slice its own git worktree on its own branch (`git worktree add`), then launch one spawn_subagent per slice, "
            "all in one message, each told to work only in its worktree.",
        ),
    ],
}

# Codex's flow commands, written as skills in `.agents/skills/`, the one project folder Codex reads skills from
# (codex 0.156); a person runs one as `$aidd-<flow>`. The lead spawns each role as its custom agent
# (`.codex/agents/aidd-<role>.toml`), and a Task worktree is `git worktree add`.
_SPAWN = "Start each role as its custom agent, such as `aidd-developer`: ask Codex to spawn it by name. Its agent file names its model, so pass none."
CODEX_LEAD = {
    "Pass the `model` in every Agent call: the alias the role's agent file names. If it names a full model id or `inherit`, pass none. "
    "Read-only search helpers (Explore) take an execution-tier role's alias.": _SPAWN,
    "Start each command in a fresh session (or after `/clear`).": "Start each command in a fresh session (`/new`).",
    "with one Edit (Write only a new or mostly rewritten file)": "with one `apply_patch` (rewrite a whole file only when it is new or mostly rewritten)",
}

_WORKTREES = "Give each {0} its own git worktree on its own branch (`git worktree add`), then spawn one subagent per {0}, all at once, each told to work only in its worktree."

CODEX_COMMANDS: dict[str, list[tuple[str, str]]] = {
    **COMMANDS,
    "autopilot.md": [
        (
            "Read the step's command file, `${CLAUDE_PLUGIN_ROOT}/commands/<flow>.md`, follow its steps",
            "Read the step's command file, `.agents/skills/aidd-<flow>/SKILL.md`, follow its steps",
        ),
        ('one Agent call per step with `isolation: "worktree"`, all in one message.', _WORKTREES.format("step")),
        ("A person stops the run with Esc, or by telling you to stop.", "A person stops the run by telling you to stop."),
    ],
    "implement.md": [
        ("skill with the Skill tool before your first edit", "skill before your first edit"),
        (
            'Make one Agent call per Task with `isolation: "worktree"`, all launched in one message. Each Task then builds '
            "in its own git worktree, on its own branch.",
            _WORKTREES.format("Task"),
        ),
    ],
    "mvp.md": [
        ('Make one Agent call per slice with `isolation: "worktree"`, all launched in one message.', _WORKTREES.format("slice")),
    ],
}

# Codex and Antigravity both read `.agents/skills/`, so where both are wired, one flow file serves both: Codex's
# commands, which name no tool only one of them has, and a lead that names how each starts a role.
SHARED_SKILLS_LEAD = {
    **CODEX_LEAD,
    "Pass the `model` in every Agent call: the alias the role's agent file names. If it names a full model id or `inherit`, pass none. "
    "Read-only search helpers (Explore) take an execution-tier role's alias.": (
        "Start each role as its own agent, such as `aidd-developer`: with the `invoke_subagent` tool in Antigravity, by "
        "asking Codex to spawn it by name, or with your harness's own subagent or custom-agent tool. Where the harness has no "
        "agent file for the role, give the subagent the role's file, `.agents/roles/aidd-<role>.md`, to follow. Where it "
        "has no subagents at all, hand a role that checks your work to a fresh session of its own. Pass no model."
    ),
    "Start each command in a fresh session (or after `/clear`).": "Start each command in a fresh session.",
    "with one Edit (Write only a new or mostly rewritten file)": EDIT,
}

# Where Codex and Antigravity share one flow file, the lead names its own harness to `next`.
SHARED_COMMANDS: dict[str, list[tuple[str, str]]] = {**CODEX_COMMANDS}

_LEAD = {"antigravity": ANTIGRAVITY_LEAD, "grok-build": GROK_LEAD, "codex": CODEX_LEAD, "agents-skills": SHARED_SKILLS_LEAD}
_COMMANDS = {"antigravity": ANTIGRAVITY_COMMANDS, "grok-build": GROK_COMMANDS, "codex": CODEX_COMMANDS, "agents-skills": SHARED_COMMANDS}
# Codex runs a flow skill as `$aidd-<flow>` (harness_files._codex_skill), so its text names each flow that way. A path
# such as `.opencode/commands/aidd-<flow>.md` keeps its slash: a word or a dot comes before it.
_SLASH_FLOW = re.compile(r"(?<![\w./-])/aidd-(?=[a-z<])")


def lead_block(harness: str = "opencode") -> str:
    """The lead's rules for one harness: `roles:lead` with the rules that name Claude Code's tools reworded."""
    swaps = _LEAD.get(harness, LEAD)
    rules = []
    for i, rule in enumerate(knowledge.roles()["loop"]["lead"], 1):
        for old, new in swaps.items():
            rule = rule.replace(old, new)
        rules.append(f"{i}. {rule}")
    return "**You are the lead.** You run this command and the roles do its work:\n\n" + "\n".join(rules) + "\n"


def command(name: str, body: str, harness: str = "opencode") -> str:
    """The body of command `name` (such as `implement.md`) for one harness: its own lead block, and each swap."""
    body = _LEAD_BLOCK.sub(lambda _: lead_block(harness), body)
    table = _COMMANDS.get(harness, COMMANDS)
    for old, new in table.get(name, []):
        body = body.replace(old, new)
    if harness == "codex":
        return _SLASH_FLOW.sub("$aidd-", body)
    return both_flow_names(body) if harness == "agents-skills" else body
