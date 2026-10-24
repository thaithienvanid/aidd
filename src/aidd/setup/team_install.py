"""The aidd-team roles without the plugin (`aidd init --team`): each role as a coding agent's own agent file, the flow
commands, the domain packs, and the short AGENTS.md section that points to them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from aidd import config, knowledge
from aidd.kernel import documents, repo_paths, resources
from aidd.setup import antigravity_wiring, codex_wiring, files, harness_files, harness_text

TEAM_PREFIX = "aidd-"  # installed names: an agent `aidd-developer`, a skill `aidd-code-review`, a command `/aidd-implement`
# The roles reference an installed agent file points to for its standards and practice skills: without the plugin,
# the team skill is not installed, so the reference is written into the repository, readable by every harness.
TEAM_ROLES_REF = ".aidd/team-roles.md"


def _team_text(text: str) -> str:
    """A plugin file as a project file: `aidd-team:<name>` becomes `aidd-<name>`, and the front matter's `name` gains the prefix.
    Project agents and skills are not namespaced by a plugin, so an unprefixed `code-review` or `developer` would
    collide with a built-in or a project's own agent, and the guard treats only `aidd-<role>` as a role.
    """
    text = text.replace(knowledge.ROLE_REFERENCE, f"the team roles reference (`{TEAM_ROLES_REF}`)")
    text = text.replace("aidd-team:", TEAM_PREFIX)
    # The aidd skill is `aidd:aidd` in the plugin and the project skill `aidd` that `aidd init` vendors.
    text = text.replace(f"\n  - {knowledge.CORE_SKILL}\n", "\n  - aidd\n")
    if text.startswith("---\n"):
        end = text.index("\n---", 4)
        front = re.sub(r"^name: (?!aidd-)", f"name: {TEAM_PREFIX}", text[:end], count=1, flags=re.M)
        text = front + text[end:]
    return text


def _front_and_body(text: str) -> tuple[dict[str, str], str]:
    end = text.index("\n---", 4)
    front = {}
    for line in text[4:end].splitlines():
        m = re.match(r"^([\w-]+): (.*)$", line)
        if m:
            value = m.group(2).strip()
            front[m.group(1)] = json.loads(value) if value.startswith('"') else value
    return front, text[end + 4 :].lstrip("\n")


def _native_agent(harness: str, name: str, front: dict[str, str], body: str, model: str | None = None) -> tuple[str, str]:
    """(path, text) of one role as `harness`'s own agent file, in the format its documentation gives (checked 2026-09-28).

    `model`, the role's `provider/model` from `agents.models`, goes into the harness's own model field when it can
    run it (`agent_models`); otherwise the file says why the harness's default runs instead."""
    tools = frozenset(t.strip() for t in front.get("tools", "").split(",") if t.strip())
    value = knowledge.harness_model(harness, model) if model else None
    note = knowledge.unsupported_note(model) if model and not value and model != knowledge.INHERIT_MODEL else None
    role = harness_files.Role(name, front["description"], harness_text.agent(harness, body), tools, value, note)
    return harness_files.AGENT_FILES[harness](role)


def flow_command_paths(flow: str) -> list[str]:
    """Where `aidd init --team` writes flow command `flow` (such as `autopilot`) as a repository file, for each harness
    that holds one: Claude Code's command, then each `harness_files.FLOW_FILES` path. Each runs as `/aidd-<flow>`."""
    name = TEAM_PREFIX + flow
    return list(dict.fromkeys([f".claude/commands/{name}.md", *(kind.path(name) for kind in harness_files.FLOW_FILES.values())]))


def flow_command_file(harness: str, flow: str) -> str | None:
    """Where `aidd init --team` writes flow command `flow` for `harness` (Claude Code's command, or the harness's own
    `harness_files.FLOW_FILES` file), or None for a harness that holds no flow commands."""
    name = TEAM_PREFIX + flow
    if harness == "claude-code":
        return f".claude/commands/{name}.md"
    kind = harness_files.FLOW_FILES.get(harness)
    return kind.path(name) if kind else None


def flow_command_name(harness: str, flow: str) -> str:
    """What a person types to run flow command `flow` in `harness`: `$aidd-<flow>` in Codex, which runs a skill by `$`
    (`harness_files._codex_skill`), and `/aidd-<flow>` everywhere else."""
    return ("$" if harness == "codex" else "/") + TEAM_PREFIX + flow


def _flow_file(harness: str, src: Path) -> dict[str, str]:
    """{path: text} of flow command `src` (such as `implement.md`) as `harness`'s own command: the shared command text,
    with the `aidd-team:<role>` and `/aidd-team:<flow>` references renamed to the `aidd-<name>` files, in the format
    and the words of that harness (`harness_files.FLOW_FILES`, `harness_text`)."""
    front, body = _front_and_body(_team_text(src.read_text(encoding="utf-8")))
    flow, kind = TEAM_PREFIX + src.stem, harness_files.FLOW_FILES[harness]
    return {kind.path(flow): kind.render(src.name, flow, front["description"], body), **(kind.extra(flow) if kind.extra else {})}


def _claude_agent(text: str, model: str | None) -> str:
    """A Claude Code agent file with the role's configured model in its `model:` field, or a note when the configured
    model is not Claude's, in which case the tier's value stays."""
    if not model:
        return text
    value = knowledge.harness_model("claude-code", model)
    line = f"model: {value}" if value else r"\g<0>\n# " + knowledge.unsupported_note(model)
    return re.sub(r"^model: .*$", line, text, count=1, flags=re.M)


def configured_models(root: Path) -> dict[str, str]:
    """`agents.models` from the repository's config: tier or role name to `provider/model`; empty without a config."""
    try:
        cfg = config.load_file(config.CONFIG_PATH, str(root))
    except (OSError, config.ConfigError, documents.DocumentError, RuntimeError):
        return {}
    return dict(cfg.get("agents", "models", default={}) or {})


NATIVE_AGENT_HARNESSES = tuple(harness_files.AGENT_FILES)


def team_files(harnesses: list[str], claude_files: bool = True, models: dict[str, str] | None = None) -> dict[str, str]:
    """Every file `aidd init --team` writes, by repository path: what install writes and uninstall compares against.

    `models` is `agents.models`; each role's resolved model goes into each harness's own model field."""
    team = resources.data_dir("team")
    out: dict[str, str] = {}
    agents = sorted((team / "agents").glob("*.md"))
    chosen = {src.stem: knowledge.resolve_agent_model(models or {}, src.stem) for src in agents}
    if claude_files:
        for src in agents:
            out[f".claude/agents/{TEAM_PREFIX}{src.name}"] = _claude_agent(_team_text(src.read_text(encoding="utf-8")), chosen[src.stem])
        for pack in sorted(p for p in (team / "skills").glob("*/SKILL.md") if p.parent.name != "aidd-team"):
            out[f".claude/skills/{TEAM_PREFIX}{pack.parent.name}/SKILL.md"] = _team_text(pack.read_text(encoding="utf-8"))
        for src in sorted((team / "commands").glob("*.md")):
            out[f".claude/commands/{TEAM_PREFIX}{src.name}"] = _team_text(src.read_text(encoding="utf-8"))
    for h in (h for h in NATIVE_AGENT_HARNESSES if h in harnesses):
        for src in agents:
            front, body = _front_and_body(_team_text(src.read_text(encoding="utf-8")))
            path, text = _native_agent(h, front["name"], front, body, chosen[src.stem])
            out[path] = text
    for h in harness_files.flow_kinds(harnesses):  # the flows as the harness's own commands, from the same source
        for src in sorted((team / "commands").glob("*.md")):
            out.update(_flow_file(h, src))
    for h in (h for h in harness_files.EXTRA_FILES if h in harnesses):
        out.update(harness_files.EXTRA_FILES[h](claude_files))
    if out:
        ref = harness_text.shared(_team_text((team / "skills" / "aidd-team" / "references" / "roles.md").read_text(encoding="utf-8")))
        # Codex runs a flow as `$aidd-<flow>`, so where it reads the reference, each flow is named both ways.
        out[TEAM_ROLES_REF] = harness_text.both_flow_names(ref) if "codex" in harnesses else ref
    return out


def team_file_variants(models: dict[str, str] | None = None) -> dict[str, set[str]]:
    """Every text `aidd init --team` may have written at each path, whichever harnesses it wired: a path two harnesses
    share (`.agents/skills/`, Antigravity's and Codex's) holds one harness's text or the shared one."""
    out: dict[str, set[str]] = {}
    for wired in [[h] for h in NATIVE_AGENT_HARNESSES] + [list(NATIVE_AGENT_HARNESSES)]:
        for rel, text in team_files(wired, True, models).items():
            out.setdefault(rel, set()).add(text)
    return out


def harness_paths() -> dict[str, set[str]]:
    """The team files only one harness gets, by harness, so a file there says that harness was wired."""
    each = {h: set(team_files([h], False)) - {TEAM_ROLES_REF} for h in NATIVE_AGENT_HARNESSES}
    return {h: paths - set().union(*(each[o] for o in each if o != h)) for h, paths in each.items()}


def _flow_owner(kind: str) -> str:
    """The harness a flow file kind is for, by its label; the shared `.agents/skills/` kind is both of its harnesses'."""
    members = harness_files.SHARED_FLOWS.get(kind, (kind,))
    return " and ".join(config.HARNESSES[m].label for m in members)


def team_section(harnesses: list[str], claude_files: bool = True) -> str:
    """The short AGENTS.md section: where the role files are, what each harness's guard holds, and one row per role."""
    roles = knowledge.roles()
    claude = f"`.claude/agents/{TEAM_PREFIX}<role>.md` (Claude Code; plain Markdown any agent can read)"
    where = [claude if claude_files else "the aidd-team plugin (`aidd-team:<role>`) for Claude Code"]
    for h in (h for h in NATIVE_AGENT_HARNESSES if h in harnesses):
        path, _ = _native_agent(h, f"{TEAM_PREFIX}<role>", {"description": ""}, "")
        where.append(f"`{path}` ({config.HARNESSES[h].label})")
    lines = [
        config.TEAM_MARK,
        "## Team roles (aidd-team)",
        "",
        "The aidd-team roles are agent files, one per role: " + "; ".join(where) + ". "
        "When you are asked to act as a role, read its file first and follow its playbook and loop contract; "
        "write only its area and hand off everything else. No role approves, merges, or chooses the route. "
        "A message that starts with `/aidd-<flow>` (`$aidd-<flow>` in Codex) is a team command: first read its flow file, named below, "
        "and follow it step by step as its lead, never from memory."
        + (
            f' Each flow is `.claude/commands/{TEAM_PREFIX}<flow>.md`: when asked to run one ("run the fix flow"), read it and follow it.'
            if claude_files
            else ""
        )
        + "".join(
            f" In {_flow_owner(kind)}, each flow is `{harness_files.FLOW_FILES[kind].path(TEAM_PREFIX + '<flow>')}`."
            for kind in harness_files.flow_kinds(harnesses)
        ),
        "",
        "In an agent where aidd wires no guard, the team is advisory: no hook checks a role's writes or stops an approval, "
        "so each role only follows its instructions, and the `aidd/gate` check decides what merges."
        + "".join(
            f" On {config.HARNESSES[h].label} the guard in `{path}` stops an approval and checks each write, but cannot tell which role made it."
            for h, path in (("codex", codex_wiring.HOOKS_FILE), ("antigravity", antigravity_wiring.HOOKS_FILE))
            if h in harnesses
        )
        + (
            " On Grok Build the guard in `.grok/hooks/aidd.json` reads `subagentType` and checks a role's writes once the folder is trusted."
            if "grok-build" in harnesses
            else ""
        )
        + (" On OpenCode the guard plugin `.opencode/plugins/aidd.js` reads the agent's name and checks a role's writes." if "opencode" in harnesses else ""),
        "",
        "| Role | Loop steps | Writes |",
        "| --- | --- | --- |",
    ]
    for key in roles["order"]:
        r = roles["roles"][key]
        lines.append(f"| `{TEAM_PREFIX}{key}` | {knowledge.role_loop(r)} | {knowledge.role_writes(r['writes'])} |")
    return "\n".join(lines) + "\n"


def install_team(root: Path, actions: list[str], force: bool = False, claude_files: bool = True, harnesses: list[str] | None = None) -> None:
    """The aidd-team roles without the plugin: Claude Code project agents, commands, domain packs, and practice skills
    named `aidd-<name>`; the roles as native agent files for Codex, Copilot, Antigravity, OpenCode, Kiro, and Grok Build
    when they are in use (with the flow commands for OpenCode, Antigravity, Grok Build, and Codex); and a short AGENTS.md section that points at them."""
    wanted = list(harnesses or [])
    for rel, text in team_files(wanted, claude_files, configured_models(root)).items():
        files.write_file(root / rel, text, force, actions)
    agents = root / "AGENTS.md"
    current = agents.read_text(encoding="utf-8") if agents.exists() else "# Agents\n"
    if config.TEAM_MARK in current:
        actions.append(f"kept     {repo_paths.shown(agents)} (already has the team section)")
        return
    with open(agents, "w", encoding="utf-8") as fh:
        fh.write(current.rstrip("\n") + "\n\n" + team_section(wanted, claude_files))
    actions.append(f"updated  {repo_paths.shown(agents)} (team roles)")
