"""The aidd-team roles without the plugin (`aidd init --team`): each role as a coding agent's own agent file, the flow
commands, the domain packs, and the short AGENTS.md section that points to them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from aidd import config, knowledge
from aidd.kernel import documents, repo_paths, resources
from aidd.setup import files, harness_files, harness_text

TEAM_PREFIX = "aidd-"  # installed names: an agent `aidd-developer`, a skill `aidd-code-review`, a command `/aidd-implement`
# The roles reference an installed agent file points to for its standards and practice skills: without the plugin,
# the team skill is not installed, so the reference is written into the repository, readable by every harness.
TEAM_ROLES_REF = ".aidd/team-roles.md"
# Each role as plain text, for a harness with subagents but no agent files aidd writes: the lead hands the file over.
GENERIC_ROLES = ".agents/roles"  # committed: a folder in .aidd/ is ignored output (config.layout)
# The security-guidance plugin (Claude Code, official marketplace) loads this file as extra context for its model-backed
# reviews, 8 KB at most beside the user's own (https://code.claude.com/docs/en/security-guidance, read 2026-11-04). It
# holds the default rules of `aidd-team:secure-coding`, so a project adds its own threat model below them.
SECURITY_GUIDANCE = ".claude/claude-security-guidance.md"


def security_guidance_text() -> str:
    """The file's text, from `templates/claude-security-guidance.md`."""
    return (resources.data_dir("templates") / "claude-security-guidance.md").read_text(encoding="utf-8")


def _team_text(text: str) -> str:
    """A plugin file as a project file: `aidd-team:<name>` becomes `aidd-<name>`, and the front matter's `name` gains the prefix.
    Project agents and skills are not namespaced by a plugin, so an unprefixed `code-review` or `developer` would
    collide with a built-in or a project's own agent.
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


def _flow_file(harness: str, src: Path) -> dict[str, str]:
    """{path: text} of flow command `src` (such as `implement.md`) as `harness`'s own command: the shared command text,
    with the `aidd-team:<role>` and `/aidd-team:<flow>` references renamed to the `aidd-<name>` files, in the format
    and the words of that harness (`harness_files.FLOW_FILES`, `harness_text`)."""
    front, body = _front_and_body(_team_text(src.read_text(encoding="utf-8")))
    flow, layout = TEAM_PREFIX + src.stem, harness_files.FLOW_FILES[harness]
    return {layout.path(flow): layout.render(src.name, flow, front["description"], body), **(layout.extra(flow) if layout.extra else {})}


def _claude_agent(text: str, model: str | None, effort: str | None = None) -> str:
    """A Claude Code agent file with the role's configured model in its `model:` field, or a note when the configured
    model is not Claude's, in which case the tier's value stays; and its configured `effort:`."""
    if effort:
        text = re.sub(r"^effort: .*$", f"effort: {effort}", text, count=1, flags=re.M)
    if not model:
        return text
    value = knowledge.harness_model("claude-code", model)
    line = f"model: {value}" if value else r"\g<0>\n# " + knowledge.unsupported_note(model)
    return re.sub(r"^model: .*$", line, text, count=1, flags=re.M)


def agent_setting(root: Path, key: str) -> dict[str, str]:
    """`agents.<key>` (`models` or `effort`) from the repository's config: tier or role name to its value; empty without a
    config."""
    try:
        cfg = config.load_file(config.CONFIG_PATH, str(root))
    except (OSError, config.ConfigError, documents.DocumentError, RuntimeError):
        return {}
    return dict(cfg.get("agents", key, default={}) or {})


def _named(roles: list[str]) -> str:
    """`the verifier`, `the verifier and the reviewer`, or `the developer, the verifier, and the reviewer`."""
    names = [f"the {r}" for r in roles]
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])}{',' if len(names) > 2 else ''} and {names[-1]}"


def independent_review_problem(models: dict[str, str], harnesses: tuple[str, ...] = ()) -> str | None:
    """Why `agents.models` does not put the verifier and the reviewer on another provider than the developer's, or None
    when it does. A role with no `provider/model` (or `inherit`) runs on the session's model, which aidd cannot see. A
    wired harness that cannot run a role's provider, such as Claude Code with an `openai/` model, runs the session's
    model instead, so the split holds only where every harness that runs the role can select it."""
    roles = ("developer", "verifier", "reviewer")
    chosen = {r: knowledge.resolve_agent_model(models, r) for r in roles}
    provider = {r: m.split("/", 1)[0] if m and m != knowledge.INHERIT_MODEL else None for r, m in chosen.items()}
    blind = [r for r in roles if provider[r] is None]
    if blind:
        return f"{_named(blind)} {'has' if len(blind) == 1 else 'have'} no provider/model in agents.models, so aidd cannot see which provider runs {'it' if len(blind) == 1 else 'them'}"
    same = [r for r in roles[1:] if provider[r] == provider["developer"]]
    if same:
        return f"{_named(same)} {'runs' if len(same) == 1 else 'run'} on {provider['developer']}, the developer's provider"
    for h in harnesses:
        unable = [r for r in roles[1:] if knowledge.harness_model(h, str(chosen[r])) is None]
        if unable:
            return f"{h} cannot run {_named(unable)}'s model, so the session's model runs {'it' if len(unable) == 1 else 'them'} there"
    return None


def independent_review_note(root: Path, harnesses: tuple[str, ...] = ()) -> str | None:
    """The `warn` line for `agents.independent_review: true` when `agents.models` does not deliver it on the wired
    `harnesses`; else None."""
    try:
        cfg = config.load_file(config.CONFIG_PATH, str(root))
    except (OSError, config.ConfigError, documents.DocumentError, RuntimeError):
        return None
    if cfg.get("agents", "independent_review", default=False) is not True:
        return None
    why = independent_review_problem(agent_setting(root, "models"), harnesses)
    if why is None:
        return None
    return f"warn     agents.independent_review is on, but {why}; set agents.models.developer, .verifier, and .reviewer so the verifier and the reviewer run on another provider that each wired harness can select"


NATIVE_AGENT_HARNESSES = tuple(harness_files.AGENT_FILES)


def team_files(harnesses: list[str], claude_files: bool = True, models: dict[str, str] | None = None, efforts: dict[str, str] | None = None) -> dict[str, str]:
    """Every file `aidd init --team` writes, by repository path: what install writes and uninstall compares against.

    `models` is `agents.models`; each role's resolved model goes into each harness's own model field. `efforts` is
    `agents.effort`, which aidd writes only into Claude Code's `effort:`."""
    team = resources.data_dir("team")
    out: dict[str, str] = {}
    agents = sorted((team / "agents").glob("*.md"))
    chosen = {src.stem: knowledge.resolve_agent_model(models or {}, src.stem) for src in agents}
    if claude_files:
        for src in agents:
            effort = knowledge.resolve_agent_effort(efforts, src.stem) if efforts else None
            out[f".claude/agents/{TEAM_PREFIX}{src.name}"] = _claude_agent(_team_text(src.read_text(encoding="utf-8")), chosen[src.stem], effort)
        for pack in sorted(p for p in (team / "skills").glob("*/SKILL.md") if p.parent.name != "aidd-team"):
            out[f".claude/skills/{TEAM_PREFIX}{pack.parent.name}/SKILL.md"] = _team_text(pack.read_text(encoding="utf-8"))
        for src in sorted((team / "commands").glob("*.md")):
            out[f".claude/commands/{TEAM_PREFIX}{src.name}"] = _team_text(src.read_text(encoding="utf-8"))
    for h in (h for h in NATIVE_AGENT_HARNESSES if h in harnesses):
        for src in agents:
            front, body = _front_and_body(_team_text(src.read_text(encoding="utf-8")))
            path, text = _native_agent(h, front["name"], front, body, chosen[src.stem])
            out[path] = text
    if harness_files.generic_readers(harnesses):  # a role's file a lead hands its subagent, where the harness has none
        for src in agents:
            front, body = _front_and_body(_team_text(src.read_text(encoding="utf-8")))
            out[f"{GENERIC_ROLES}/{front['name']}.md"] = harness_text.agent("agents-skills", body)
    for h in harness_files.flow_labels(harnesses):  # the flows as the harness's own commands, from the same source
        for src in sorted((team / "commands").glob("*.md")):
            out.update(_flow_file(h, src))
    for h in (h for h in harness_files.EXTRA_FILES if h in harnesses):
        out.update(harness_files.EXTRA_FILES[h](claude_files))
    if out:
        ref = harness_text.shared(_team_text((team / "skills" / "aidd-team" / "references" / "roles.md").read_text(encoding="utf-8")))
        # Codex runs a flow as `$aidd-<flow>`, so where it reads the reference, each flow is named both ways.
        out[TEAM_ROLES_REF] = harness_text.both_flow_names(ref) if "codex" in harnesses else ref
    return out


def team_file_variants(models: dict[str, str] | None = None, efforts: dict[str, str] | None = None) -> dict[str, set[str]]:
    """Every text `aidd init --team` may have written at each path, whichever harnesses it wired: a path two harnesses
    share (`.agents/skills/`, Antigravity's and Codex's) holds one harness's text or the shared one."""
    out: dict[str, set[str]] = {}
    readers = ["cursor"]  # any harness that reads `.agents/skills/` with no agent files of aidd's: the shared flows and the roles' files
    for wired in [[h] for h in NATIVE_AGENT_HARNESSES] + [list(NATIVE_AGENT_HARNESSES), readers, [*NATIVE_AGENT_HARNESSES, *readers]]:
        for rel, text in team_files(wired, True, models, efforts).items():
            out.setdefault(rel, set()).add(text)
    out[SECURITY_GUIDANCE] = {security_guidance_text()}  # written once, never upgraded, so a changed copy stays
    return out


def harness_paths() -> dict[str, set[str]]:
    """The team files only one harness gets, by harness, so a file there says that harness was wired."""
    each = {h: set(team_files([h], False)) - {TEAM_ROLES_REF} for h in NATIVE_AGENT_HARNESSES}
    return {h: paths - set().union(*(each[o] for o in each if o != h)) for h, paths in each.items()}


def _flow_owner(label: str) -> str:
    """The harness a flow file is for, by its label; the shared `.agents/skills/` flow file is both of its harnesses'."""
    members = harness_files.SHARED_FLOWS.get(label, (label,))
    return " and ".join(config.HARNESSES[m].label for m in members)


def team_section(harnesses: list[str], claude_files: bool = True) -> str:
    """The short AGENTS.md section: where the role files are, and one row per role."""
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
        "write only its area and hand off everything else. No role decides for a person: on an ask, the lead asks and waits. "
        "A message that starts with `/aidd-<flow>` (`$aidd-<flow>` in Codex) is a team command: first read its flow file, named below, "
        "and follow it step by step as its lead, never from memory."
        + (
            f' Each flow is `.claude/commands/{TEAM_PREFIX}<flow>.md`: when asked to run one ("run the fix flow"), read it and follow it.'
            if claude_files
            else ""
        )
        + "".join(
            f" In {_flow_owner(label)}, each flow is `{harness_files.FLOW_FILES[label].path(TEAM_PREFIX + '<flow>')}`."
            for label in harness_files.flow_labels(harnesses)
        ),
        "",
        "Every role follows the risk rules: before an action it checks the level (`aidd risk`), acts on allow, says what it "
        "did on report, and on ask hands the question to the lead, who asks the person. No hook checks a role's writes: "
        "each role follows its instructions, and its area is a guide.",
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
    for rel, text in team_files(wanted, claude_files, agent_setting(root, "models"), agent_setting(root, "effort")).items():
        files.write_file(root / rel, text, force, actions)
    if claude_files or "claude-code" in wanted:  # a project file, so it is written with or without the aidd-team plugin
        files.write_file(root / SECURITY_GUIDANCE, security_guidance_text(), False, actions)  # the project adds its own rules, so even --force keeps it
    runs_roles = (("claude-code",) if claude_files or "claude-code" in wanted else ()) + tuple(h for h in NATIVE_AGENT_HARNESSES if h in wanted)
    if note := independent_review_note(root, runs_roles):
        actions.append(note)
    agents = root / "AGENTS.md"
    current = agents.read_text(encoding="utf-8") if agents.exists() else "# Agents\n"
    if config.TEAM_MARK in current:
        actions.append(f"kept     {repo_paths.shown(agents)} (already has the team section)")
        return
    with open(agents, "w", encoding="utf-8") as fh:
        fh.write(current.rstrip("\n") + "\n\n" + team_section(wanted, claude_files))
    actions.append(f"updated  {repo_paths.shown(agents)} (team roles)")
