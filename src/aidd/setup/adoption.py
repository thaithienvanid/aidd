"""Adopt a repository (`aidd init`): the config, the vendored skill and its links, the CI files, the review policy, the
coding agents' pointer files, the MCP server, the harness ask rules, and the team.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from aidd import __version__, config, risk
from aidd.kernel import git, repo_paths, resources, text
from aidd.setup import claude_plugins as setup_claude_plugins
from aidd.setup import config_template, detection, files, ignore_lines, marked_sections, mcp_wiring, pins, team_install

SKILL_REL = ".agents/skills/aidd"
DEFAULT_LINKS = (".claude/skills",)
AGENTS_MARK = marked_sections.AGENTS_MARK
GITIGNORE_LINE = config.OUTPUT_IGNORE
# Environment files hold secrets; the example beside them does not. Written under ENV_MARK, which uninstall looks for.
ENV_IGNORE = (".env*", "!.env.example")
ENV_MARK = "# aidd: environment files hold secrets; .env.example stays"
GITHUB_WORKFLOWS = ("aidd-tests.yml",)
# The product's security scanning (dependency scan, SAST, SBOM, secret scan): written when compliance is on (a target),
# or with `--security-ci`; and Dependabot, written for the ecosystems init finds.
SECURITY_WORKFLOW = "aidd-security.yml"
GITLAB_SECURITY = "aidd-security.gitlab-ci.yml"
# The ruleset a person imports on GitHub: the default branch takes no force-push and no deletion, and merges through a
# pull request whose aidd tests pass. aidd never changes a platform's settings itself.
GITHUB_RULESETS = ("main.json",)
# `aidd init --devcontainer`: the optional dev container with default-deny egress, copied from templates/devcontainer/.
DEVCONTAINER_FILES = ("devcontainer.json", "Dockerfile", "init-firewall.sh")


def detect_harnesses(root: Path) -> list[str]:
    """The coding agents this repository uses: a folder or file of theirs in it. Never what this machine has installed,
    so init and doctor say the same thing on every teammate's machine; `--harness` names the rest. A folder that holds
    only what `aidd init` itself linked into it (`_only_aidds`) is no sign: init run twice then finds the same agents."""
    return [key for key, h in config.HARNESSES.items() if any((root / x).exists() and not _only_aidds(root / x) for x in h.repo)]


def session_harnesses(env: dict[str, str]) -> list[str]:
    """The coding agents whose own variable this environment carries (`config.SESSION_ENV`): the agent that runs
    `aidd init` in its shell. When two are set, as when one agent starts another, both count, so init wires both."""
    return list(dict.fromkeys(h for var, h in config.SESSION_ENV.items() if env.get(var)))


def init_harnesses(root: Path, env: dict[str, str] | None = None) -> list[str]:
    """The coding agents init wires with no `--harness`: the ones this repository shows (`detect_harnesses`), then the
    ones that run this session (`session_harnesses`), so an agent that runs `aidd init` gets its own ask rules."""
    found = detect_harnesses(root)
    return found + [h for h in session_harnesses(dict(os.environ) if env is None else env) if h not in found]


def _evidence(root: Path, detected: list[str]) -> list[str]:
    """What showed each detected agent: its file or folder in the repository, as `detect_harnesses` found it, else the
    variable its session set."""
    shown = []
    for key in detected:
        hit = next((x for x in config.HARNESSES[key].repo if (root / x).exists() and not _only_aidds(root / x)), None)
        if hit:
            shown.append(hit + ("/" if (root / hit).is_dir() else ""))
        else:
            shown += [f"this session's {var}" for var, h in config.SESSION_ENV.items() if h == key and os.environ.get(var)][:1]
    return shown


def no_ask_rules_hint(installed: list[str], named: bool = False) -> str:
    """The line init prints when no agent it wired takes ask rules, so nothing stops an agent at an ask: the exact
    command that writes them, for the agents this machine has, else for each agent aidd writes them for. `named`: the
    agents came from `--harness`, so none was looked for."""
    keys = [h for h in installed if config.HARNESSES[h].ask_rules]
    if keys:
        how = "`aidd init " + " ".join(f"--harness {h}" for h in keys) + "` writes them"
    else:
        how = f"`aidd init --harness <agent>` writes them for yours: {text.series([h.key for h in config.ask_rule_harnesses()], 'or')}"
    which = "no agent you named takes them" if named else "no agent found here takes them"
    return f"hint     no ask rules written: {which}, so no agent stops at an ask by itself. {how}"


def _only_aidds(folder: Path) -> bool:
    """`.claude/` that shows no wiring: empty, or holding only the skill link `aidd init --link .claude/skills` writes
    (`skills/aidd`), Claude Code's own `worktrees/`, and `settings.local.json`, which are this machine's state, not the
    repository's setup."""
    if folder.name != ".claude" or not folder.is_dir():
        return False
    try:
        names = {p.name for p in folder.iterdir()}
        return names <= {"skills", "worktrees", "settings.local.json"} and (
            "skills" not in names or [p.name for p in (folder / "skills").iterdir()] == ["aidd"]
        )
    except OSError:
        return False


def installed_harnesses(*, home: Path | None = None, path: str | None = None) -> list[str]:
    """The coding agents this machine has (a folder in the home directory, or a binary on PATH): only a hint that
    init prints for the ones whose wiring matters and that the repository does not show yet."""
    home = home if home is not None else Path.home()
    env_path = os.environ.get("PATH", "") if path is None else path
    return [
        key
        for key, h in config.HARNESSES.items()
        if any((home / x).exists() for x in h.home) or any(shutil.which(b, path=env_path) is not None for b in h.bins)
    ]


def agents_to_restart(actions: list[str], root: Path, wired: list[str] | None = None) -> list[str]:
    """The coding agents that load what `init` wrote only when a session starts: each agent one of whose own files or
    folders (`config.HARNESSES`, `repo`) init wrote, updated, or linked, such as Claude Code's `.claude/` and
    `.mcp.json` or OpenCode's `.opencode/`, and Claude Code when init installed a plugin. A file it kept does not count.
    Each path is read relative to `root`, so a repository that itself sits under such a folder never counts. With
    `wired`, the agents init wired (named with --harness, or detected), only those count: `--team` writes the domain
    packs into `.claude/skills/` for every agent, which is no reason to restart a Claude Code nobody asked for."""
    top = root.resolve()
    found: set[str] = set()
    plugin = False
    for a in actions:
        verb, _, rest = a.partition(" ")
        if verb == "ran" and "claude plugin install" in rest:
            plugin = True
        if verb not in ("wrote", "updated", "linked", "copied"):
            continue
        shown = Path(rest.strip().split(" (", 1)[0].split(" -> ", 1)[0])
        try:
            parts = (shown if shown.is_absolute() else root / shown).resolve().relative_to(top).parts
        except ValueError:
            continue
        found.update(key for key, h in config.HARNESSES.items() if any(parts[: len(Path(x).parts)] == Path(x).parts for x in h.repo))
    if wired is not None:
        found &= set(wired)
    found |= {"claude-code"} if plugin else set()
    return [h.label for key, h in config.HARNESSES.items() if key in found]


def restart_notice(agents: list[str], actions: list[str] | tuple[str, ...] = ()) -> str:
    """The line after init that names each agent to restart (`agents_to_restart`), then, from what init did (`actions`),
    each question the restart brings and the answer to it, so none of them surprises the person."""
    each = "each loads" if len(agents) > 1 else "it loads"
    line = f"Restart {text.series(agents, 'and')} in this folder: {each} aidd's skill, MCP server, and ask rules only when a session starts."
    asks = restart_questions(agents, actions) if actions else []
    return "\n".join([line, "When it starts:", *asks] if asks else [line])


def restart_questions(agents: list[str], actions: list[str] | tuple[str, ...]) -> list[str]:
    """Each question a restart brings, with its answer: the folder trust of each agent that has a trust step, the plugins
    `.claude/settings.json` now enables, and the `aidd` server in `.mcp.json`. aidd's own MCP tools need no answer, and
    the last line says why."""
    out = []
    for h in config.HARNESSES.values():
        if h.label in agents and h.trust is not None:
            # The restart already starts the agent in the repository, so only the answer is left of the trust step.
            answer = re.sub(r"^start `[^`]+` in the repository and ", "", h.trust.how)
            out.append(f"- {h.label}: trust this folder? Yes: {answer}, so it loads the settings aidd wrote.")
    enabled = [a.split("(enables ", 1)[1].split(":", 1)[0] for a in actions if a.startswith("updated  .claude/settings.json (enables ")]
    if enabled:
        out.append(
            f"- Claude Code: install the plugins `.claude/settings.json` enables ({', '.join(enabled)})? Yes: they carry aidd's skill and its MCP server."
        )
    if any(a.split()[:2] in (["wrote", ".mcp.json"], ["updated", ".mcp.json"]) for a in actions):
        out.append("- Claude Code: use the `aidd` MCP server in `.mcp.json`? Yes, so your agent gets aidd's tools.")
    if any("aidd's MCP tools" in a and "run with no prompt" in a for a in actions if a.startswith(("updated", "wrote"))):
        out.append("- aidd's own MCP tools then run with no question, because the settings aidd wrote allow them.")
    return out


REVIEW_POLICY = "REVIEW.md"


def write_review_policy(root: Path, actions: list[str]) -> None:
    """The review policy every reviewer reads, written once and never replaced, even with --force: after init it is the
    repository's own policy, and uninstall removes it only unchanged."""
    path = root / REVIEW_POLICY
    if path.exists():
        actions.append(f"kept     {repo_paths.shown(path)} (the repository's review policy)")
        return
    files.write_file(path, review_policy_template(), False, actions)


# `aidd init --team` puts the code-review practice skill in the repository; Claude Code Review reads a skill file named
# on a line of REVIEW.md's own (and only from a protected branch), so the policy names it, after the template's text.
REVIEW_SKILL_FILE = f".claude/skills/{team_install.TEAM_PREFIX}code-review/SKILL.md"
REVIEW_SKILL_BLOCK = f"\n## Practice skill\n\n@{REVIEW_SKILL_FILE}\n"


def review_policy_template() -> str:
    return (resources.data_dir("templates") / REVIEW_POLICY).read_text(encoding="utf-8")


def include_review_skill(root: Path, actions: list[str]) -> None:
    """Name the installed code-review skill in an unedited REVIEW.md, for a review service that includes it. A policy a
    person changed, or a skill the team plugin carries instead of the repository, is left as it is."""
    path = root / REVIEW_POLICY
    if not (root / REVIEW_SKILL_FILE).is_file() or not path.is_file():
        return
    if path.read_text(encoding="utf-8") != review_policy_template():
        return
    path.write_text(review_policy_template() + REVIEW_SKILL_BLOCK, encoding="utf-8")
    actions.append(f"updated  {repo_paths.shown(path)} (names the code-review skill, which Claude Code Review includes)")


def vendor_skill(root: Path, force: bool, actions: list[str]) -> None:
    src = resources.data_dir("skill")
    dest = root / SKILL_REL
    if dest.resolve() == src.resolve():
        actions.append(f"kept     {repo_paths.shown(dest)} (this is the source)")
        return
    if dest.exists() and not force:
        actions.append(f"kept     {repo_paths.shown(dest)} (exists; `aidd upgrade --yes` upgrades it)")
        return
    if dest.is_symlink() or dest.is_file():
        dest.unlink()
    elif dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    actions.append(f"vendored {repo_paths.shown(dest)} (aidd {__version__})")


def link_skill(root: Path, link_dir: str, actions: list[str], force: bool = False) -> None:
    link = root / link_dir / "aidd"
    target = os.path.relpath(root / SKILL_REL, link.parent)
    if link.is_symlink() and os.readlink(link) == target:
        actions.append(f"kept     {repo_paths.shown(link)} -> {repo_paths.shown(target)}")
        return
    if link.is_symlink() or link.exists():
        if not force:
            why = "a link elsewhere; --force replaces it" if link.is_symlink() else "a real directory; --force refreshes it"
            actions.append(f"kept     {repo_paths.shown(link)} ({why})")
            return
        if link.is_symlink():
            link.unlink()
        else:
            shutil.rmtree(link)
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=True)
        actions.append(f"linked   {repo_paths.shown(link)} -> {repo_paths.shown(target)}")
    except OSError:
        shutil.copytree(root / SKILL_REL, link)
        actions.append(f"copied   {repo_paths.shown(link)} (symlinks unavailable; `aidd doctor` checks it stays equal)")


@dataclass(frozen=True)
class InitOptions:
    """What `aidd init` was asked for, as one object: the CLI fills it from its flags and what `detection` found, and
    `init` reads nothing else. A new option is one field here and one line where the CLI fills it."""

    profile: str
    ci: str
    links: list[str]
    skill: bool = True
    force: bool = False
    approvers: list[str] | None = None
    specialists: dict[str, list[str]] | None = None
    test: list[str] | None = None
    team: bool = False
    harnesses: list[str] | None = None
    claude_plugins: bool = False
    ref: str | None = None
    devcontainer: bool = False
    risk_areas: list[dict] | None = None
    stack: list[str] | None = None
    ui: bool = True
    compliance_targets: list[str] | None = None
    security_ci: bool = False
    existing_code: bool = False
    delegate: bool = False
    merge_deploys: bool | None = None


def ruleset_text(template: str, profile: str) -> str:
    """The branch ruleset for `profile`: under `team`, merging needs one approving review, and the approval of the last
    push, so the platform holds a second person's yes; under `solo`, neither, since one person decides, and GitHub never
    lets a person approve their own push, so the last-push rule would block every merge."""
    if profile != "team":
        return template
    return template.replace('"required_approving_review_count": 0', '"required_approving_review_count": 1').replace(
        '"require_last_push_approval": false', '"require_last_push_approval": true'
    )


def push_rule_branches(root: Path) -> list[str]:
    """The branches the ask rules for a push to the default branch name: the default branch when the repository tells
    it, else every branch that could be it (`kernel.git.default_branches`), so a harness asks for more, never less. A
    local-only repository whose trunk has another name, adopted on a setup branch, keeps its trunk guarded."""
    return git.default_branches(str(root))[0]


def default_branch_note(branches: list[str]) -> str:
    """What init and doctor say when git cannot tell the default branch: a push to each branch that could be it asks,
    and how to name it."""
    return (
        "git cannot tell the default branch (no origin/HEAD, and no main or master), so a push to any branch that could "
        f"be it asks: {', '.join(branches)}. To name it, run `git remote set-head origin --auto` once there is a remote, "
        "or `git config init.defaultBranch <branch>`, then `aidd upgrade --yes`"
    )


def delegation_text(root: Path, options: InitOptions, actions: list[str]) -> str | None:
    """The `delegation` block for `aidd init --delegate`, with what it found and its three notes in `actions`; None
    without the flag. Under `team`, the recommended answer is still "ask me each time"."""
    from aidd.setup import delegation_wiring

    if not options.delegate:
        return None
    name = git.run(["config", "user.name"], str(root), check=False).strip()
    email = git.run(["config", "user.email"], str(root), check=False).strip()
    if not name or not email:
        raise ValueError(
            "--delegate names you as the one it acts for: set `git config user.name` and `user.email`, or your no-reply address, then run it again"
        )
    if options.profile == "team":
        actions.append("note     under team, the recommended answer is to ask you each time; a delegated merge and a major Spec stay a person's review")
    if "claude-code" not in (options.harnesses or []) and not (root / ".claude").exists():
        actions.append("note     only Claude Code answers a delegated ask in this version; your other coding agents keep asking you every time")
    found = delegation_wiring.deploy_files(root)
    if options.merge_deploys is None:
        shown = f" It found {', '.join(found)}." if found else ""
        actions.append(
            f"note     does merging to the default branch deploy anything?{shown} Unsure, so default_branch_deploys stays unset and a merge stays yours"
        )
    actions += [f"note     {n}" for n in delegation_wiring.NOTES]
    return delegation_wiring.block(f"{name} <{email}>", push_rule_branches(root)[0], options.merge_deploys, dt.date.today())


def write_ask_rules(root: Path, harnesses: list[str], actions: list[str], *, write: bool = True, config_text: str | None = None) -> None:
    """Each detected agent's ask rules, from the risk rules in force (`risk.apply_harness_rules`). `config_text` is the
    config as a dry run would leave it, in place of the file."""
    try:
        cfg = config.load_file(config.CONFIG_PATH, str(root), text=config_text) if (root / config.CONFIG_PATH).is_file() else None
    except (config.ConfigError, OSError, ValueError) as exc:
        actions.append(f"skipped  the ask rules: the config cannot be read ({exc})")
        return
    rs = risk.rule_set(cfg)
    branches, known = git.default_branches(str(root))
    patterns, read_paths = risk.harness_patterns(rs, branches), risk.harness_read_paths(rs)
    if not known and any(config.HARNESSES[key].ask_rules for key in harnesses):
        actions.append(f"hint     {default_branch_note(branches)}")
    for key in harnesses:
        fmt = config.HARNESSES[key].ask_rules
        if not fmt:
            continue
        try:
            done = risk.apply_harness_rules(root, fmt, patterns, read_paths=read_paths, write=write)
        except (ValueError, OSError) as exc:
            actions.append(f"kept     {config.HARNESSES[key].label}'s settings ({exc})")
            continue
        actions += [f"{d.split(' ', 1)[0]:<8} {d.split(' ', 1)[1]}" for d in done] or [f"kept     {config.HARNESSES[key].label}'s ask rules (up to date)"]
    if "claude-code" in harnesses:
        from aidd.setup import delegation_wiring

        try:
            actions += [f"{d.split(' ', 1)[0]:<8} {d.split(' ', 1)[1]}" for d in delegation_wiring.apply(root, cfg, write=write)]
        except (ValueError, OSError) as exc:
            actions.append(f"kept     Claude Code's settings, with no delegation hooks ({exc})")


@dataclass(frozen=True)
class _AgentWiring:
    """What init decides about the coding agents before it writes their files: the agents to wire, whether Claude Code
    is among them, the plugins it relies on, and the plugin fallback. The later steps read this, never the agents
    first detected, because the fallback adds Claude Code to them."""

    detected: list[str]
    claude: bool
    claude_plugins: bool
    plugin_on: bool
    fell_back: bool
    installed_now: list[str]
    why_not: str


def init(root: Path, options: InitOptions) -> list[str]:
    """Adopt. Coding agents are detected (or given as `harnesses`) and each one is wired the way it reads instructions
    (`config.harnesses`): Claude Code gets the `.claude/skills` link and the MCP server, unless the plugins carry them
    (`claude_plugins`, or the aidd plugin in the person's own settings); an agent with its own instruction file gets a
    pointer file; the rest read AGENTS.md. Every agent with an ask-rule format gets the ask risk rules. On GitHub the
    test workflow and the default branch's ruleset are written, with the security scans when compliance is on."""
    actions: list[str] = []
    resources.data_dir("templates")  # an install without its templates fails here, before a plugin is installed or a file written
    wiring = _agent_wiring(root, options, _harnesses_to_wire(root, options, actions), actions)
    _write_config(root, options, actions)
    _vendor_and_link_skill(root, options, wiring, actions)
    snippet = agents_snippet(root, options.skill)
    _pointer(root / "AGENTS.md", "# Agents\n\n", snippet, actions)
    ci_from = len(actions)
    pinned = _ci_pin(options, actions)
    _write_devcontainer(root, options, actions)
    if options.ci == "github":
        _write_github_files(root, options, pinned, actions)
    elif options.ci == "gitlab":
        _write_gitlab_files(root, options, pinned, actions)
    _drop_unused_pin(actions, ci_from)
    _wire_mcp(root, options, wiring, actions)
    write_ask_rules(root, wiring.detected, actions)
    if options.harnesses != [] and not any(config.HARNESSES[h].ask_rules for h in wiring.detected):
        actions.append(no_ask_rules_hint(installed_harnesses(), named=options.harnesses is not None))
    _write_team_files(root, options, wiring, actions)
    _write_pointers(root, wiring, snippet, actions)
    _update_gitignore(root, actions)
    if wiring.fell_back:
        actions.append(setup_claude_plugins.plugin_fallback_note(root, wiring.installed_now, wiring.why_not))
    return actions


def _harnesses_to_wire(root: Path, options: InitOptions, actions: list[str]) -> list[str]:
    """The coding agents to wire: the ones named with `--harness`, else the ones this repository shows. Says which, and
    hints at the agents this machine has that the repository does not show yet."""
    detected = init_harnesses(root) if options.harnesses is None else list(options.harnesses)
    source = " (--harness)" if options.harnesses is not None else f" (found {', '.join(_evidence(root, detected))})"
    none = "no coding agent's files in this repository; AGENTS.md and .agents/skills/ serve any agent that reads them"
    actions.append("detected " + (", ".join(config.HARNESSES[h].label for h in detected) + source if detected else none))
    # With no agent that takes ask rules, init's `no_ask_rules_hint` names the agents this machine has instead.
    if options.harnesses is None and any(config.HARNESSES[h].ask_rules for h in detected):
        wired = [
            h
            for h in installed_harnesses()
            if h not in detected
            and (h == "claude-code" or config.HARNESSES[h].ask_rules or (config.HARNESSES[h].pointer and not config.HARNESSES[h].only_if_present))
            and not (h == "claude-code" and f"aidd@{config.MARKETPLACE}" in config.user_plugins_enabled())
        ]
        if wired:
            labels, flags = ", ".join(config.HARNESSES[h].label for h in wired), " ".join(f"--harness {h}" for h in wired)
            actions.append(f"hint     this machine has {labels}: wire {'it' if len(wired) == 1 else 'them'} with {flags}")
    return detected


def _agent_wiring(root: Path, options: InitOptions, detected: list[str], actions: list[str]) -> _AgentWiring:
    """How Claude Code is wired: through the plugins (installed here, or enabled in the person's own settings) or through
    repository files. A plugin install that cannot run falls back to the files, and Claude Code joins the agents."""
    claude = "claude-code" in detected
    claude_plugins, fell_back, installed_now, why_not = options.claude_plugins, False, list[str](), ""
    if claude_plugins:
        why_not, installed_now = setup_claude_plugins.install_claude_plugins(root, actions, team=options.team)
        claude_plugins, fell_back = not why_not, bool(why_not)
        if fell_back and not claude:
            claude, detected = True, [*detected, "claude-code"]
    # The aidd plugin this user enabled carries the MCP server and the skill: the project enables it for everyone who
    # works here (`share_with_project`) instead of copying them, so none loads twice.
    plugin_on = claude and not claude_plugins and f"aidd@{config.MARKETPLACE}" in config.user_plugins_enabled()
    return _AgentWiring(detected, claude, claude_plugins, plugin_on, fell_back, installed_now, why_not)


def _write_config(root: Path, options: InitOptions, actions: list[str]) -> None:
    """The config, the Specs folder's README, and the review policy, with the hints about what the config holds."""
    tpl = resources.data_dir("templates")
    cfg_text = config_template.config_text(
        config_template.ConfigTemplate(
            options.profile,
            approvers=options.approvers,
            specialists=options.specialists,
            test=options.test,
            test_name="smoke" if options.test == config_template.SMOKE_TEST else "unit",
            default_owner_team=config_template.SOLO_TEAM if options.profile == "solo" else None,
            risk_areas=options.risk_areas,
            stack=options.stack,
            preview=config_template.preview_command(root),
            ui=options.ui,
            compliance_targets=options.compliance_targets,
            repo=config_template.origin_repo(root),
            existing_code=options.existing_code,
            delegation=delegation_text(root, options, actions),
        )
    )
    files.write_file(root / config.CONFIG_PATH, cfg_text, options.force, actions)
    config_written = actions[-1].startswith("wrote")  # a config that exists is kept, with what a person chose in it
    if options.existing_code and config_written:
        actions.append(
            "hint     kept the existing structure: `project.defaults.disabled` names modular_monolith. To adopt the modular monolith, "
            "a person accepts an ADR and deletes that line (aidd-team:modular-monolith)"
        )
    if options.risk_areas and config_written:
        found = ", ".join(f"{r['name']} ({', '.join(r['paths'][:2])})" for r in options.risk_areas[:4])
        actions.append(f"risk     wrote the sensitive areas it found as `risks.areas`, each asked before an edit: {found}; remove any that is wrong")
    files.write_file(root / "specs" / "README.md", (tpl / "specs-README.md").read_text(encoding="utf-8"), options.force, actions)
    write_review_policy(root, actions)


def _vendor_and_link_skill(root: Path, options: InitOptions, wiring: _AgentWiring, actions: list[str]) -> None:
    """The vendored skill, and its links for the agents that read a skills folder of their own."""
    if not options.skill:
        return
    vendor_skill(root, options.force, actions)
    for d in dict.fromkeys([*DEFAULT_LINKS, *options.links]) if wiring.claude and not wiring.claude_plugins else options.links:
        if (wiring.claude_plugins or wiring.plugin_on) and d in DEFAULT_LINKS:
            actions.append(f"skipped  {repo_paths.shown(d)}/aidd (the aidd plugin ships the skill; a link would load it twice)")
            continue
        link_skill(root, d, actions, options.force)


def agents_snippet(root: Path, skill: bool) -> str:
    """The marked section every agent's instruction file carries, with the verification block for the tests configured.
    Without the vendored `skill`, it tells the agent to load the plugin's."""
    snippet = (resources.data_dir("templates") / "AGENTS.snippet.md").read_text(encoding="utf-8")
    if not skill:
        snippet = snippet.replace("load the skill at `.agents/skills/aidd/SKILL.md`", "load the `aidd` skill (installed as a plugin)")
    block = config_template.verification_block(config_template.configured_tests(root))
    return snippet.rstrip("\n") + "\n\n" + block.rstrip("\n") + "\n" + marked_sections.end_mark(AGENTS_MARK) + "\n"


def _ci_pin(options: InitOptions, actions: list[str]) -> tuple[str | None, str | None]:
    """The aidd ref (and its release tag) the CI files pin, with a line that says it or hints at pinning one."""
    if options.ci not in ("github", "gitlab"):
        return None, None
    pin, release, why = pins.resolve_pin(options.ref)
    if pin:
        actions.append(f"pinned   the aidd workflow to {pin}" + why)
    else:
        actions.append(f"hint     pin the aidd workflow to a commit SHA: `aidd upgrade --yes` after a release (it names v{__version__})")
    return pin, release


def _write_devcontainer(root: Path, options: InitOptions, actions: list[str]) -> None:
    """The optional dev container (`--devcontainer`)."""
    if not options.devcontainer:
        return
    tpl = resources.data_dir("templates")
    for name in DEVCONTAINER_FILES:
        files.write_file(root / ".devcontainer" / name, (tpl / "devcontainer" / name).read_text(encoding="utf-8"), options.force, actions)


def _write_github_files(root: Path, options: InitOptions, pinned: tuple[str | None, str | None], actions: list[str]) -> None:
    """The test workflow, the pull request template, the default branch's ruleset, the security workflow when compliance
    is on (or `--security-ci`), and Dependabot."""
    tpl = resources.data_dir("templates")
    pin, release = pinned
    pr_tpl = (tpl / "github" / "pull_request_template.md").read_text(encoding="utf-8")
    on = bool(options.compliance_targets)
    why = "--security-ci" if options.security_ci else "compliance targets"
    for name in GITHUB_WORKFLOWS:
        body = pins.pin_workflow((tpl / "github" / name).read_text(encoding="utf-8"), pin, release)
        files.write_file(root / ".github" / "workflows" / name, body, options.force, actions)
    files.write_file(root / ".github" / "pull_request_template.md", pr_tpl, options.force, actions)
    before = len(actions)
    for name in GITHUB_RULESETS:
        files.write_file(
            root / ".github" / "rulesets" / name,
            ruleset_text((tpl / "github" / "rulesets" / name).read_text(encoding="utf-8"), options.profile),
            options.force,
            actions,
        )
    if any(a.startswith("wrote") for a in actions[before:]):
        actions.append(
            "hint     import .github/rulesets/main.json in Settings → Rules → Rulesets → Import a ruleset: it is the hard stop on the "
            "default branch (no force-push, no deletion, merges through a pull request with green tests); aidd never changes a platform's settings"
        )
    if options.security_ci or on:
        before = len(actions)
        files.write_file(
            root / ".github" / "workflows" / SECURITY_WORKFLOW, (tpl / "github" / SECURITY_WORKFLOW).read_text(encoding="utf-8"), options.force, actions
        )
        actions[before] += f" ({why}: dependency scan, SAST, an SBOM, and a secret scan)"
    files.write_file(root / config_template.DEPENDABOT, config_template.dependabot_text(root), options.force, actions)


def _write_gitlab_files(root: Path, options: InitOptions, pinned: tuple[str | None, str | None], actions: list[str]) -> None:
    """The test pipeline, the merge request template, and the security pipeline when compliance is on (or `--security-ci`)."""
    tpl = resources.data_dir("templates")
    pin, release = pinned
    pr_tpl = (tpl / "github" / "pull_request_template.md").read_text(encoding="utf-8")
    on = bool(options.compliance_targets)
    why = "--security-ci" if options.security_ci else "compliance targets"
    body = pins.pin_workflow((tpl / "gitlab" / "aidd.gitlab-ci.yml").read_text(encoding="utf-8"), pin, release)
    files.write_file(root / ".gitlab" / "aidd.gitlab-ci.yml", body, options.force, actions)
    files.write_file(root / ".gitlab" / "merge_request_templates" / "Default.md", pr_tpl, options.force, actions)
    actions.append("hint     add `include: {local: .gitlab/aidd.gitlab-ci.yml}` to .gitlab-ci.yml, and protect the default branch")
    if options.security_ci or on:
        before = len(actions)
        files.write_file(root / ".gitlab" / GITLAB_SECURITY, (tpl / "gitlab" / GITLAB_SECURITY).read_text(encoding="utf-8"), options.force, actions)
        actions[before] += f" ({why}: a secret scan)"
        actions.append(f"hint     add `- local: .gitlab/{GITLAB_SECURITY}` to the include in .gitlab-ci.yml")


def _drop_unused_pin(actions: list[str], ci_from: int) -> None:
    """Forget the pin line when every workflow was kept as it is: each names the pin it had, not this one."""
    if (
        actions[ci_from : ci_from + 1]
        and actions[ci_from].startswith("pinned")
        and not any(a.startswith("wrote") and (".github/workflows/" in a or ".gitlab/" in a) for a in actions[ci_from:])
    ):
        del actions[ci_from]


def _wire_mcp(root: Path, options: InitOptions, wiring: _AgentWiring, actions: list[str]) -> None:
    """The aidd MCP server for Claude Code and Codex, and the Claude Code plugins the project enables in its place."""
    wire = wiring.claude and not wiring.claude_plugins and not wiring.plugin_on
    if not wire and wiring.claude and (wiring.claude_plugins or wiring.plugin_on):
        team_plugin = options.team and (wiring.claude_plugins or f"aidd-team@{config.MARKETPLACE}" in config.user_plugins_enabled())
        wire = not setup_claude_plugins.share_with_project(root, actions, team=team_plugin)
    if wire:
        mcp_wiring.install_user_launcher(root, actions)
        mcp_wiring.install_claude_mcp(root, actions)
    # aidd's own MCP tools run with no prompt, by the name Claude Code gives them: the server's, or the plugin's, and
    # only where that one is on, so a plugin the project turned off gets nothing.
    if wire:
        mcp_wiring.allow_claude_tools(root, actions, mcp_wiring.CLAUDE_TOOL_PREFIXES[0])
    elif wiring.claude and mcp_wiring.project_enables_plugin(root):
        mcp_wiring.allow_claude_tools(root, actions, mcp_wiring.CLAUDE_TOOL_PREFIXES[1])
        mcp_wiring.withdraw_server_tools(root, actions)  # the server's names, once `.mcp.json` names no server
    if "codex" in wiring.detected:
        if not wire:
            mcp_wiring.install_user_launcher(root, actions)
        mcp_wiring.install_codex_mcp(root, actions)


def _write_team_files(root: Path, options: InitOptions, wiring: _AgentWiring, actions: list[str]) -> None:
    """The delivery team (`--team`): its files for each agent, unless the aidd-team plugin carries them."""
    if not options.team:
        return
    team_plugin = wiring.claude_plugins or f"aidd-team@{config.MARKETPLACE}" in config.user_plugins_enabled()
    if team_plugin and not wiring.claude_plugins:
        actions.append(f"skipped  .claude/ team files (the aidd-team@{config.MARKETPLACE} plugin is enabled and carries the roles and commands)")
    team_install.install_team(root, actions, options.force, claude_files=not team_plugin, harnesses=wiring.detected)
    include_review_skill(root, actions)


def _write_pointers(root: Path, wiring: _AgentWiring, snippet: str, actions: list[str]) -> None:
    """The instruction file of each agent that has one of its own, carrying the same marked section as AGENTS.md."""
    for h in (config.HARNESSES[k] for k in wiring.detected):
        if h.pointer and (not h.only_if_present or (root / h.pointer).is_file()):
            _pointer(root / h.pointer, h.header, snippet, actions)


def _update_gitignore(root: Path, actions: list[str]) -> None:
    """The ignore lines aidd's outputs, the environment files, and the stack's build outputs need, added once."""
    gi = root / ".gitignore"
    current = gi.read_text(encoding="utf-8") if gi.exists() else ""
    have = current.splitlines()
    ignore_outputs = ignore_lines.missing_ignore_lines(root, current, detection.stack_names(root))
    add = ([GITIGNORE_LINE] if GITIGNORE_LINE not in have else []) + ([ENV_MARK, *ENV_IGNORE] if ENV_IGNORE[0] not in have else []) + ignore_outputs
    if add:
        with open(gi, "a", encoding="utf-8") as fh:
            fh.write(("\n" if current and not current.endswith("\n") else "") + "".join(f"{line}\n" for line in add))
        reasons = (["environment files stay out of git, except .env.example"] if ENV_MARK in add else []) + (
            [ignore_lines.ignore_lines_reason(ignore_outputs)] if ignore_outputs else []
        )
        actions.append(f"updated  {repo_paths.shown(gi)}" + (f" ({'; '.join(reasons)})" if reasons else ""))


def _pointer(path: Path, header: str, snippet: str, actions: list[str]) -> None:
    """A harness-specific instruction file that carries the same marked section as AGENTS.md."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(header + snippet, encoding="utf-8")
        actions.append(f"wrote    {repo_paths.shown(path)}")
    elif AGENTS_MARK not in path.read_text(encoding="utf-8"):
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n" + snippet)
        actions.append(f"appended {repo_paths.shown(path)}")
    else:
        actions.append(f"kept     {repo_paths.shown(path)} (already points at the skill)")
