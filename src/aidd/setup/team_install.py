"""The aidd-team roles without the plugin (`aidd init --aidd-team`): each role as a coding agent's own agent file, the flow
commands, the domain packs, and the short AGENTS.md section that points to them.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from aidd import config, knowledge
from aidd.kernel import documents, regular_files, repo_paths, resources
from aidd.kernel import text as kernel_text
from aidd.setup import domain_packs, files, harness_files, harness_text, marked_sections, team_record
from aidd.setup.domain_packs import TEAM_PREFIX

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
    """A plugin file as a project file: `aidd-team:<name>` and `aidd-packs:<name>` become `aidd-<name>`, and the front matter's `name` gains the prefix.
    Project agents and skills are not namespaced by a plugin, so an unprefixed `code-review` or `developer` would
    collide with a built-in or a project's own agent.
    """
    text = text.replace(knowledge.ROLE_REFERENCE, f"the team roles reference (`{TEAM_ROLES_REF}`)")
    text = text.replace("aidd-team:", TEAM_PREFIX).replace(f"{config.PACKS_PLUGIN}:", TEAM_PREFIX)
    text = re.sub(r"\]\(\.\./(?!aidd-)([a-z][a-z0-9-]*)/", rf"](../{TEAM_PREFIX}\1/", text)  # a link from one skill to another's folder
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
    front, body = _front_and_body(_team_text(src.read_text(encoding="utf-8")))  # aidd's own: the bundled team files
    flow, layout = TEAM_PREFIX + src.stem, harness_files.FLOW_FILES[harness]
    return {layout.path(flow): layout.render(src.name, flow, front["description"], body), **(layout.extra(flow) if layout.extra else {})}


def _claude_agent(text: str, model: str | None, effort: str | None = None, turns: int | None = None) -> str:
    """A Claude Code agent file with the role's configured model in its `model:` field, or a note when the configured
    model is not Claude's, in which case the tier's value stays; and its configured `effort:` and `maxTurns:`."""
    if effort:
        text = re.sub(r"^effort: .*$", f"effort: {effort}", text, count=1, flags=re.M)
    if turns:
        text = re.sub(r"^maxTurns: .*$", f"maxTurns: {turns}", text, count=1, flags=re.M)
    if not model:
        return text
    value = knowledge.harness_model("claude-code", model)
    tier_value = re.search(r"^model: (.*)$", text, flags=re.M)
    line = f"model: {value}" if value else r"\g<0>\n# " + knowledge.unsupported_note(model, tier_value.group(1).strip() if tier_value else None)
    return re.sub(r"^model: .*$", line, text, count=1, flags=re.M)


def agent_setting(root: Path, key: str) -> dict:
    """`agents.<key>` (`models`, `effort`, or `max_turns`) from the repository's config: tier or role name to its value; empty
    without a config."""
    try:
        cfg = config.load_file(config.CONFIG_PATH, str(root))
    except (OSError, config.ConfigError, documents.DocumentError, RuntimeError):
        return {}
    return dict(cfg.get("agents", key, default={}) or {})


def agent_settings(root: Path) -> dict[str, dict]:
    """The repository's `agents.effort` and `agents.max_turns`, which `team_files` writes into Claude Code's agent files."""
    return {key: agent_setting(root, key) for key in ("effort", "max_turns")}


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


def wanted_team_files(root: Path) -> tuple[dict[str, str], list[str], bool] | None:
    """What `aidd upgrade` writes for the team files already in this repository: each path with its text, the harnesses
    those files wire, and whether Claude Code's own files are among them. None when aidd wrote no team file here."""
    installed = [rel for rel in team_files(list(NATIVE_AGENT_HARNESSES), True) if (root / rel).is_file()]
    if not installed:
        return None
    claude = any(rel.startswith(".claude/") for rel in installed)
    own = harness_paths()  # a path two harnesses share says neither was wired
    harnesses = [h for h in NATIVE_AGENT_HARNESSES if any(rel in own[h] for rel in installed)]
    packs = domain_packs.choose(root).packs if claude else None
    return team_files(harnesses, claude, agent_setting(root, "models"), agent_settings(root), packs), harnesses, claude


def models_inert_note(root: Path) -> str | None:
    """When `agents.models`, `agents.effort`, or `agents.max_turns` is set while the aidd-team plugin carries Claude Code's roles:
    the setting changes none of the plugin's agent files, which name each tier's own model, effort, and turn limit. Else None."""
    keys = [f"agents.{k}" for k in ("models", "effort", "max_turns") if agent_setting(root, k)]
    if not keys:
        return None
    return (
        f"{kernel_text.series(keys, 'and')} {'is' if len(keys) == 1 else 'are'} set, but the aidd-team plugin carries the roles in Claude Code, and its agent files name "
        "each tier's own model, effort, and turn limit, so the setting changes only the other agents' files. To apply it in Claude Code too, turn the plugin off in "
        "your Claude Code settings and run `aidd init --aidd-team`"
    )


def team_plugin_carries_roles(root: Path) -> bool:
    """Whether Claude Code loads the aidd-team roles from the plugin here, read as Claude Code reads its settings."""
    return f"aidd-team@{config.MARKETPLACE}" in config.plugins_enabled(root)


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


# The roles whose answer only Claude Code's hook verifies, so only Claude Code gets their file.
CLAUDE_CODE_ONLY_ROLES = ("delegate",)


def _skill_files(skill: Path) -> dict[str, str]:
    """{path: text} of a team skill as a project skill: its `SKILL.md` and the files it links (`references/`), beside it. Inside
    `rendered_once`, the same skill is read once, whatever arguments `team_files` is asked with: it is most of a render."""
    rendered = _RENDERED.get()
    if rendered is not None and ("skill", skill) in rendered:
        return rendered["skill", skill]
    folder = f".claude/skills/{TEAM_PREFIX}{skill.name}"
    files = sorted(f for f in skill.rglob("*") if f.is_file())
    found = {f"{folder}/{f.relative_to(skill).as_posix()}": _team_text(f.read_text(encoding="utf-8")) for f in files}  # aidd's own: the bundled team files
    if rendered is not None:
        rendered["skill", skill] = found
    return found


# Inside `rendered_once`: each answer of `team_files`, by its arguments, and each skill's files, so a command renders the same files once.
_RENDERED: contextvars.ContextVar[dict[object, dict[str, str]] | None] = contextvars.ContextVar("team_files_rendered", default=None)


@contextlib.contextmanager
def rendered_once() -> Iterator[None]:
    """Inside it, `team_files` renders each set of arguments once and answers a copy after. The files are the ones aidd ships,
    which no command changes, but the render reads every agent, skill, and command file, so a command that asks again
    (`harness_paths`, `wanted_team_files`, the doctor's listing) pays for it each time. It is for the work of one command and
    never outlives it. A scope inside another shares the outer one's."""
    if _RENDERED.get() is not None:
        yield
        return
    token = _RENDERED.set({})
    try:
        yield
    finally:
        _RENDERED.reset(token)


def team_files(
    harnesses: list[str],
    claude_files: bool = True,
    models: dict[str, str] | None = None,
    settings: dict[str, dict] | None = None,
    packs: list[str] | None = None,
) -> dict[str, str]:
    """Every file `aidd init --aidd-team` writes, by repository path: what install writes and uninstall compares against.

    `models` is `agents.models`; each role's resolved model goes into each harness's own model field. `settings`
    holds `agents.effort` and `agents.max_turns` (`agent_settings`), which aidd writes only into Claude Code's `effort:` and `maxTurns:`. `packs` is the domain packs to write beside
    every practice skill (`domain_packs.choose`); None writes every pack, the files aidd may have written anywhere."""
    rendered = _RENDERED.get()
    if rendered is None:
        return _render_team_files(harnesses, claude_files, models, settings, packs)
    key = json.dumps([harnesses, claude_files, models, settings, packs], sort_keys=True)
    if key not in rendered:
        rendered[key] = _render_team_files(harnesses, claude_files, models, settings, packs)
    return dict(rendered[key])


def _render_team_files(
    harnesses: list[str], claude_files: bool, models: dict[str, str] | None, settings: dict[str, dict] | None, packs: list[str] | None
) -> dict[str, str]:
    team = resources.data_dir("team")
    efforts, turns = (settings or {}).get("effort"), (settings or {}).get("max_turns")
    out: dict[str, str] = {}
    agents = sorted((team / "agents").glob("*.md"))
    chosen = {src.stem: knowledge.resolve_agent_model(models or {}, src.stem) for src in agents}
    if claude_files:
        for src in agents:
            effort = knowledge.resolve_agent_effort(efforts, src.stem) if efforts else None
            turn_limit = knowledge.resolve_agent_turns(turns, src.stem) if turns else None
            role = _team_text(src.read_text(encoding="utf-8"))  # aidd's own: the bundled team files
            out[f".claude/agents/{TEAM_PREFIX}{src.name}"] = _claude_agent(role, chosen[src.stem], effort, turn_limit)
        left_out = set(domain_packs.pack_names()) - set(packs) if packs is not None else set()
        practices = [p for p in (team / "skills").glob("*/SKILL.md") if p.parent.name != "aidd-team"]
        wanted_packs = [p for p in (resources.data_dir("packs") / "skills").glob("*/SKILL.md") if p.parent.name not in left_out]
        for skill in sorted([*practices, *wanted_packs], key=lambda p: p.parent.name):
            out.update(_skill_files(skill.parent))
        for src in sorted((team / "commands").glob("*.md")):
            out[f".claude/commands/{TEAM_PREFIX}{src.name}"] = _team_text(src.read_text(encoding="utf-8"))  # aidd's own: the bundled team files
    # The delegate answers only in Claude Code in this version, so every other harness gets no file for it.
    others = [src for src in agents if src.stem not in CLAUDE_CODE_ONLY_ROLES]
    for h in (h for h in NATIVE_AGENT_HARNESSES if h in harnesses):
        for src in others:
            front, body = _front_and_body(_team_text(src.read_text(encoding="utf-8")))  # aidd's own: the bundled team files
            path, text = _native_agent(h, front["name"], front, body, chosen[src.stem])
            out[path] = text
    if harness_files.generic_readers(harnesses):  # a role's file a lead hands its subagent, where the harness has none
        for src in others:
            front, body = _front_and_body(_team_text(src.read_text(encoding="utf-8")))  # aidd's own: the bundled team files
            out[f"{GENERIC_ROLES}/{front['name']}.md"] = harness_text.agent("agents-skills", body)
    for h in harness_files.flow_labels(harnesses):  # the flows as the harness's own commands, from the same source
        for src in sorted((team / "commands").glob("*.md")):
            out.update(_flow_file(h, src))
    for h in (h for h in harness_files.EXTRA_FILES if h in harnesses):
        out.update(harness_files.EXTRA_FILES[h](claude_files))
    if out:
        roles = (team / "skills" / "aidd-team" / "references" / "roles.md").read_text(encoding="utf-8")  # aidd's own: the bundled team files
        ref = harness_text.shared(_team_text(roles))
        ref = ref.rstrip("\n") + "\n" + domain_packs.packs_table()  # every pack, so a domain no risk area names is still findable
        # Codex runs a flow as `$aidd-<flow>`, so where it reads the reference, each flow is named both ways.
        out[TEAM_ROLES_REF] = harness_text.both_flow_names(ref) if "codex" in harnesses else ref
    return out


def team_file_variants(models: dict[str, str] | None = None, settings: dict[str, dict] | None = None) -> dict[str, set[str]]:
    """Every text `aidd init --aidd-team` may have written at each path, whichever harnesses it wired: a path two harnesses
    share (`.agents/skills/`, Antigravity's and Codex's) holds one harness's text or the shared one."""
    out: dict[str, set[str]] = {}
    readers = ["cursor"]  # any harness that reads `.agents/skills/` with no agent files of aidd's: the shared flows and the roles' files
    for wired in [[h] for h in NATIVE_AGENT_HARNESSES] + [list(NATIVE_AGENT_HARNESSES), readers, [*NATIVE_AGENT_HARNESSES, *readers]]:
        for rel, text in team_files(wired, True, models, settings).items():
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
    return "\n".join(lines) + "\n\n" + marked_sections.end_mark(config.TEAM_MARK) + "\n"


class InstallOptions(Protocol):
    """What `install_team` reads of `aidd init`'s options (adoption.InitOptions, which imports this module)."""

    @property
    def force(self) -> bool: ...

    @property
    def detected(self) -> dict | None: ...


def install_team(root: Path, actions: list[str], options: InstallOptions | None = None, claude_files: bool = True, harnesses: list[str] | None = None) -> None:
    """The aidd-team roles without the plugin: Claude Code project agents, commands, domain packs, and practice skills
    named `aidd-<name>`; the roles as native agent files for Codex, Copilot, Antigravity, OpenCode, Kiro, and Grok Build
    when they are in use (with the flow commands for OpenCode, Antigravity, Grok Build, and Codex); and a short AGENTS.md section that points at them.
    `options` is what `aidd init` was asked for: its `force`, and what it detected, so detection runs once."""
    wanted, force = list(harnesses or []), bool(options and options.force)
    choice = domain_packs.choose(root, options.detected if options else None) if claude_files else None
    written = team_files(wanted, claude_files, agent_setting(root, "models"), agent_settings(root), choice.packs if choice else None)
    for rel, text in written.items():
        files.write_file(root, root / rel, text, force, actions)
    team_record.write_record(root, written, actions)  # what aidd wrote, so a later upgrade or uninstall removes only that
    if choice is not None:
        actions.append(domain_packs.install_note(choice))
    if claude_files or "claude-code" in wanted:  # a project file, so it is written with or without the aidd-team plugin
        files.write_file(root, root / SECURITY_GUIDANCE, security_guidance_text(), False, actions)  # the project adds its own rules, so even --force keeps it
    runs_roles = (("claude-code",) if claude_files or "claude-code" in wanted else ()) + tuple(h for h in NATIVE_AGENT_HARNESSES if h in wanted)
    if note := independent_review_note(root, runs_roles):
        actions.append(note)
    agents = root / "AGENTS.md"
    found, why = regular_files.named_text(root, "AGENTS.md")
    if found is None and why != regular_files.MISSING:
        actions.append(f"skipped  {repo_paths.shown(agents)} ({why}: aidd neither reads it nor writes through it; replace it with the file)")
        return
    current = found or "# Agents\n"
    if config.TEAM_MARK in current:
        actions.append(f"kept     {repo_paths.shown(agents)} (already has the team section)")
        return
    if files.write_or_skip(root, agents, current.rstrip("\n") + "\n\n" + team_section(wanted, claude_files), actions):
        actions.append(f"updated  {repo_paths.shown(agents)} (team roles)")
