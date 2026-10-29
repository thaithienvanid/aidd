"""Adopt a repository (`aidd init`): the config, the vendored skill and its links, the CI files, the review policy, the
coding agents' pointer files and hooks, and the team.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from aidd import __version__, config
from aidd.kernel import repo_paths, resources, text
from aidd.setup import (
    antigravity_wiring,
    codex_wiring,
    config_template,
    detection,
    files,
    grok_wiring,
    hook_wiring,
    ignore_lines,
    opencode_wiring,
    orca_file,
    pins,
    team_install,
)
from aidd.setup import claude_plugins as setup_claude_plugins

SKILL_REL = ".agents/skills/aidd"
DEFAULT_LINKS = (".claude/skills",)
AGENTS_MARK = "<!-- aidd -->"
GITIGNORE_LINE = config.OUTPUT_IGNORE
# Environment files hold secrets; the example beside them does not. Written under ENV_MARK, which uninstall looks for.
ENV_IGNORE = (".env*", "!.env.example")
ENV_MARK = "# aidd: environment files hold secrets; .env.example stays"
GITHUB_WORKFLOWS = ("aidd-tests.yml", "aidd-gate.yml", "aidd-relay.yml")
# The product's security scanning (dependency scan, SAST, SBOM, secret scan): written when compliance is on (a target, or the audited
# profile), or with `--security-ci`; and Dependabot, written for the ecosystems init finds.
SECURITY_WORKFLOW = "aidd-security.yml"
# The GitLab side, under the same condition: the secret scan.
GITLAB_SECURITY = "aidd-security.gitlab-ci.yml"
# The rulesets a person imports on GitHub: the default branch requires `aidd/gate`; goal branches block force pushes and deletion.
GITHUB_RULESETS = ("main.json", "goal.json")
# `aidd init --devcontainer`: the optional dev container with default-deny egress, copied from templates/devcontainer/.
DEVCONTAINER_FILES = ("devcontainer.json", "Dockerfile", "init-firewall.sh")


def detect_harnesses(root: Path) -> list[str]:
    """The coding agents this repository uses: a folder or file of theirs in it. Never what this machine has installed,
    so init and doctor say the same thing on every teammate's machine; `--harness` names the rest. A folder that holds
    only what `aidd init` itself linked into it (`_only_aidds`) is no sign: init run twice then finds the same agents."""
    return [key for key, h in config.HARNESSES.items() if any((root / x).exists() and not _only_aidds(root / x) for x in h.repo)]


def _evidence(root: Path, detected: list[str]) -> list[str]:
    """The file or folder in the repository that showed each detected agent, as `detect_harnesses` found it."""
    shown = []
    for key in detected:
        hit = next((x for x in config.HARNESSES[key].repo if (root / x).exists() and not _only_aidds(root / x)), None)
        if hit:
            shown.append(hit + ("/" if (root / hit).is_dir() else ""))
    return shown


def _only_aidds(folder: Path) -> bool:
    """`.claude/` holding nothing but the skill link `aidd init --link .claude/skills` writes (`skills/aidd`)."""
    if folder.name != ".claude" or not folder.is_dir():
        return False
    try:
        return [p.name for p in folder.iterdir()] == ["skills"] and [p.name for p in (folder / "skills").iterdir()] == ["aidd"]
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


def restart_notice(agents: list[str]) -> str:
    """The line after init that names each agent to restart (`agents_to_restart`)."""
    each = "each loads" if len(agents) > 1 else "it loads"
    return f"Restart {text.series(agents, 'and')} in this folder: {each} aidd's hooks and instructions only when a session starts."


REVIEW_POLICY = "REVIEW.md"


def write_review_policy(root: Path, actions: list[str]) -> None:
    """The review policy every reviewer reads, written once and never replaced, even with --force: after init it is the
    repository's own policy, and uninstall removes it only unchanged."""
    path = root / REVIEW_POLICY
    if path.exists():
        actions.append(f"kept     {repo_paths.shown(path)} (the repository's review policy)")
        return
    files.write_file(path, (resources.data_dir("templates") / REVIEW_POLICY).read_text(encoding="utf-8"), False, actions)


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
    policy: list[str] | None = None
    goal: str | None = None
    enforce: bool = False
    claude_hooks: bool | None = None
    team: bool = False
    harnesses: list[str] | None = None
    claude_plugins: bool = False
    mods: bool = False
    ref: str | None = None
    devcontainer: bool = False
    orca: bool = False
    risk_rules: list[dict] | None = None
    stack: list[str] | None = None
    ui: bool = True
    compliance_targets: list[str] | None = None
    security_ci: bool = False
    held_commands: list[dict] | None = None
    not_held: int = 0
    existing_code: bool = False


def init(root: Path, options: InitOptions) -> list[str]:
    """Adopt. The gate starts in the profile's mode (solo and team advise, org and audited enforce) unless enforce is set;
    the CI files are pinned by `pins.resolve_pin`.

    Coding agents are detected (or given as `harnesses`) and each one is wired the way it reads instructions (`harnesses.py`):
    Claude Code gets the `.claude/skills` link, the guard hook, and the MCP server, unless `claude_hooks` is False or the
    plugins are installed instead (`claude_plugins`); an agent with its own instruction file gets a pointer file; the rest read AGENTS.md.
    `links` are extra skill directories to link whatever was detected. `devcontainer` also writes .devcontainer/ from
    templates/devcontainer/: a container that denies outbound traffic except to an allow-list, a starting point only.
    `compliance_targets` fill `project.compliance` (else it is written commented out); on GitHub, the security-scanning
    workflow is written when compliance is on (a target, or the audited profile) or with `security_ci`, and Dependabot
    for the ecosystems found, always. `held_commands` (from `detection.held_commands`, with `not_held` names past its cap) are written into a new config only:
    a config that exists is kept, so re-running init never adds an entry twice or brings back one a person deleted.
    """
    approvers, claude_plugins = options.approvers, options.claude_plugins
    actions: list[str] = []
    tpl = resources.data_dir("templates")
    detected = detect_harnesses(root) if options.harnesses is None else list(options.harnesses)
    source = " (--harness)" if options.harnesses is not None else f" (found {', '.join(_evidence(root, detected))})"
    none = "no coding agent's files in this repository; AGENTS.md and .agents/skills/ serve any agent that reads them"
    actions.append("detected " + (", ".join(config.HARNESSES[h].label for h in detected) + source if detected else none))
    if options.harnesses is None:
        # Installed here but not visible in the repository: named only where init would wire something for it.
        wired = [
            h
            for h in installed_harnesses()
            if h not in detected
            and (h == "claude-code" or (config.HARNESSES[h].pointer and not config.HARNESSES[h].only_if_present))
            # The person's own aidd plugin already brings the guard, the skill, and the MCP server to Claude Code here.
            and not (h == "claude-code" and f"aidd@{config.MARKETPLACE}" in config.user_plugins_enabled())
        ]
        if wired:
            labels, flags = ", ".join(config.HARNESSES[h].label for h in wired), " ".join(f"--harness {h}" for h in wired)
            actions.append(f"hint     this machine has {labels}: wire {'it' if len(wired) == 1 else 'them'} with {flags}")
    claude = "claude-code" in detected
    fell_back, installed_now, why_not = False, list[str](), ""
    if claude_plugins:
        why_not, installed_now = setup_claude_plugins.install_claude_plugins(root, actions, team=options.team, mods=options.mods)
        claude_plugins, fell_back = not why_not, bool(why_not)
        if fell_back and not claude:
            # The person asked for Claude Code: wire its whole repository set, not only what detection would find.
            claude, detected = True, [*detected, "claude-code"]
    elif options.mods:
        actions.append(
            f"skipped  {setup_claude_plugins.MODS}: a mod ships only as a plugin; add --claude-plugins, or run `claude plugin install {setup_claude_plugins.MODS}@{config.MARKETPLACE}`"
        )
    # The aidd plugin this user enabled carries the guard, the session hooks, the MCP server, and the skill: the project
    # enables it for everyone who works here (`share_with_project`) instead of copying them, so none loads twice. Only
    # the user's own settings count: a repository's `.claude/` files cannot claim the plugin to keep the guard unwired.
    plugin_on = claude and not claude_plugins and options.claude_hooks is None and f"aidd@{config.MARKETPLACE}" in config.user_plugins_enabled()
    if not approvers and options.profile == "solo":
        # Solo still needs a listed approver: the operator, found without the network. The email the commits carry is what
        # a local approval (`aidd approve`) is counted as; a platform login is what a PR/MR's approval is counted as.
        login, email = config.operator_login(root), config.operator_email(root)
        approvers = [*([f"@{login}"] if login else []), *([f"email:{email}"] if email else [])] or None
        if approvers:
            actions.append(f"approver {', '.join(approvers)} (the operator, from the local git and gh config; a local approval counts as the email)")
        if not login and config.gh_account_count() > 1:
            actions.append(
                "hint     gh holds more than one GitHub account, so no login was guessed: add yours with `aidd init --approvers @you,email:you@example.com --force`, or set `git config github.user you` in this repository"
            )
        else:
            actions.append("hint     name the approver: `aidd init --approvers email:you@example.com --force` (the email your commits use)")
    elif approvers and options.profile == "solo" and hook_wiring.local_first(root) and (unlisted := config.unlisted_local_approver(root, approvers)):
        listed = ",".join([*approvers, f"email:{config.operator_email(root)}"])
        actions.append(f"hint     {unlisted}: `aidd init --approvers {listed} --force`")
    # Unset unless `--enforce`: the profile's default decides (solo and team advise, org and audited enforce).
    mode = "enforce" if options.enforce else None
    cfg_text = config_template.config_text(
        config_template.ConfigTemplate(
            options.profile,
            approvers=approvers,
            specialists=options.specialists,
            test=options.test,
            policy=options.policy,
            mode=mode,
            goal=options.goal,
            test_name="smoke" if options.test == config_template.SMOKE_TEST else "unit",
            default_owner_team=config_template.SOLO_TEAM if options.profile == "solo" else None,
            risk_rules=options.risk_rules,
            stack=options.stack,
            preview=config_template.preview_command(root),
            ui=options.ui,
            compliance_targets=options.compliance_targets,
            held_commands=options.held_commands,
            repo=config_template.origin_repo(root),
            existing_code=options.existing_code,
        )
    )
    files.write_file(root / config.CONFIG_PATH, cfg_text, options.force, actions)
    config_written = actions[-1].startswith("wrote")  # a config that exists is kept, with what a person chose in it
    if options.existing_code and config_written:
        actions.append(
            "hint     kept the existing structure: `project.defaults.disabled` names modular_monolith. To adopt the modular monolith, "
            "a person accepts an ADR and deletes that line (aidd-team:modular-monolith)"
        )
    if options.held_commands and config_written:
        names = ", ".join(g["name"] for g in options.held_commands)
        actions.append(f"held     deploy and infrastructure commands for a person in `guard.held_commands`: {names}; a person may delete any")
        if options.not_held:
            actions.append(
                f"hint     {options.not_held} more deploy script names are not held (the first {detection.MAX_HELD_SCRIPTS} are); "
                "a person can add them to `guard.held_commands`"
            )
    if options.risk_rules and config_written:
        found = ", ".join(f"{r['name']} ({', '.join(r['paths'][:2])})" for r in options.risk_rules[:4])
        actions.append(f"risk     wrote the sensitive areas it found as `risk_rules`: {found}; remove any that is wrong")
    files.write_file(root / "specs" / "README.md", (tpl / "specs-README.md").read_text(encoding="utf-8"), options.force, actions)
    write_review_policy(root, actions)
    if options.skill:
        vendor_skill(root, options.force, actions)
        for d in dict.fromkeys([*DEFAULT_LINKS, *options.links]) if claude and not claude_plugins else options.links:
            if (claude_plugins or plugin_on) and d in DEFAULT_LINKS:
                actions.append(f"skipped  {repo_paths.shown(d)}/aidd (the aidd plugin ships the skill; a link would load it twice)")
                continue
            link_skill(root, d, actions, options.force)
    snippet = (tpl / "AGENTS.snippet.md").read_text(encoding="utf-8")
    if not options.skill:
        snippet = snippet.replace("load the skill at `.agents/skills/aidd/SKILL.md`", "load the `aidd` skill (installed as a plugin)")
        if no_plugin := [h for h in detected if h != "claude-code"]:
            # Only Claude Code loads the skill from a plugin: every other agent reads it from `.agents/skills/aidd`.
            actions.append(f"warn     --no-skill: {', '.join(no_plugin)} read no aidd plugin, so they get no aidd skill; run `aidd init` without --no-skill")
    snippet = snippet.rstrip("\n") + "\n\n" + config_template.verification_block(config_template.configured_tests(root))
    _pointer(root / "AGENTS.md", "# Agents\n\n", snippet, actions)
    ci_from = len(actions)
    if options.ci in ("github", "gitlab"):
        pin, release, why = pins.resolve_pin(options.ref)
        if pin:
            label = pins.pin_label(pin, release)
            actions.append(f"pinned   the aidd workflows to {pin}" + why + (f", labelled `{label[3:]}`" if label.startswith(" # aidd ") else ""))
        else:
            actions.append(
                f"hint     pin the aidd workflows to a commit SHA: `aidd upgrade --ref <sha> --yes` (they name v{__version__}; `init --force` would also replace the config)"
            )
    if options.devcontainer:
        for name in DEVCONTAINER_FILES:
            files.write_file(root / ".devcontainer" / name, (tpl / "devcontainer" / name).read_text(encoding="utf-8"), options.force, actions)
    if options.orca:
        orca_file.orca_actions(root, actions)
    pr_tpl = (tpl / "github" / "pull_request_template.md").read_text(encoding="utf-8")
    on = bool(options.compliance_targets) or options.profile == "audited"
    why = "--security-ci" if options.security_ci else "compliance targets" if options.compliance_targets else "the audited profile"
    if options.ci == "github":
        for name in GITHUB_WORKFLOWS:
            text = pins.pin_workflow((tpl / "github" / name).read_text(encoding="utf-8"), pin, release)
            if name == "aidd-gate.yml" and not options.enforce and config.profile_mode(options.profile) == "advisory":
                text = re.sub(r"(mode:\s*)enforce", r"\1advisory", text, count=1)
            files.write_file(root / ".github" / "workflows" / name, text, options.force, actions)
        files.write_file(root / ".github" / "pull_request_template.md", pr_tpl, options.force, actions)
        before = len(actions)
        for name in GITHUB_RULESETS:
            files.write_file(root / ".github" / "rulesets" / name, (tpl / "github" / "rulesets" / name).read_text(encoding="utf-8"), options.force, actions)
        if any(a.startswith("wrote") for a in actions[before:]):
            actions.append(
                "hint     import .github/rulesets/main.json and goal.json in Settings → Rules → Rulesets → Import a ruleset, then pin "
                "`aidd/gate` to your aidd App (docs/PLATFORMS.md); aidd never changes a platform's settings itself"
            )
        if options.security_ci or on:
            before = len(actions)
            files.write_file(
                root / ".github" / "workflows" / SECURITY_WORKFLOW, (tpl / "github" / SECURITY_WORKFLOW).read_text(encoding="utf-8"), options.force, actions
            )
            actions[before] += f" ({why}: dependency scan, SAST, an SBOM, and a secret scan)"
        files.write_file(root / config_template.DEPENDABOT, config_template.dependabot_text(root), options.force, actions)
    elif options.ci == "gitlab":
        # The mode is the config's `mode` key, read from the base branch; a pipeline variable cannot change it.
        text = pins.pin_workflow((tpl / "gitlab" / "aidd.gitlab-ci.yml").read_text(encoding="utf-8"), pin, release)
        files.write_file(root / ".gitlab" / "aidd.gitlab-ci.yml", text, options.force, actions)
        files.write_file(root / ".gitlab" / "merge_request_templates" / "Default.md", pr_tpl, options.force, actions)
        actions.append("hint     add `include: {local: .gitlab/aidd.gitlab-ci.yml}` to .gitlab-ci.yml")
        if options.security_ci or on:
            before = len(actions)
            files.write_file(root / ".gitlab" / GITLAB_SECURITY, (tpl / "gitlab" / GITLAB_SECURITY).read_text(encoding="utf-8"), options.force, actions)
            actions[before] += f" ({why}: a secret scan)"
            actions.append(f"hint     add `- local: .gitlab/{GITLAB_SECURITY}` to the include in .gitlab-ci.yml")
    if (
        actions[ci_from : ci_from + 1]
        and actions[ci_from].startswith("pinned")
        and not any(a.startswith("wrote") and (".github/workflows/" in a or ".gitlab/" in a) for a in actions[ci_from:])
    ):
        del actions[ci_from]  # every workflow was kept as it is, so it names the pin it had
        if options.ref:
            actions.append(f"hint     the workflows were kept with the pin they had: `aidd upgrade --ref {options.ref} --yes` pins them to it")
    wire = options.claude_hooks if options.claude_hooks is not None else (claude and not claude_plugins and not plugin_on)
    if not wire and claude and options.claude_hooks is None and (claude_plugins or plugin_on):
        team_plugin = options.team and (claude_plugins or f"aidd-team@{config.MARKETPLACE}" in config.user_plugins_enabled())
        wire = not setup_claude_plugins.share_with_project(root, actions, team=team_plugin)
    if wire:
        hook_wiring.install_claude_hooks(root, actions)
    if "antigravity" in detected and options.claude_hooks is not False:
        antigravity_wiring.install(root, actions)
    if "grok-build" in detected and options.claude_hooks is not False:
        grok_wiring.install(root, actions)
    if "codex" in detected and options.claude_hooks is not False:
        codex_wiring.install(root, actions)
    if "opencode" in detected and options.claude_hooks is not False:
        opencode_wiring.install(root, actions)
    if options.team:
        # The aidd-team plugin, installed now or enabled in the user's own settings, carries what the .claude/ team files hold.
        team_plugin = claude_plugins or f"aidd-team@{config.MARKETPLACE}" in config.user_plugins_enabled()
        if team_plugin and not claude_plugins:
            actions.append(f"skipped  .claude/ team files (the aidd-team@{config.MARKETPLACE} plugin is enabled and carries the roles and commands)")
        team_install.install_team(root, actions, options.force, claude_files=not team_plugin, harnesses=detected)
    for h in (config.HARNESSES[k] for k in detected):
        if h.pointer and (not h.only_if_present or (root / h.pointer).is_file()):
            _pointer(root / h.pointer, h.header, snippet, actions)
    gi = root / ".gitignore"
    text = gi.read_text(encoding="utf-8") if gi.exists() else ""
    have = text.splitlines()
    ignore_outputs = ignore_lines.missing_ignore_lines(root, text, detection.stack_names(root))
    add = ([GITIGNORE_LINE] if GITIGNORE_LINE not in have else []) + ([ENV_MARK, *ENV_IGNORE] if ENV_IGNORE[0] not in have else []) + ignore_outputs
    if add:
        with open(gi, "a", encoding="utf-8") as fh:
            fh.write(("\n" if text and not text.endswith("\n") else "") + "".join(f"{line}\n" for line in add))
        reasons = (["environment files stay out of git, except .env.example"] if ENV_MARK in add else []) + (
            [ignore_lines.ignore_lines_reason(ignore_outputs)] if ignore_outputs else []
        )
        actions.append(f"updated  {repo_paths.shown(gi)}" + (f" ({'; '.join(reasons)})" if reasons else ""))
    if fell_back:
        actions.append(setup_claude_plugins.plugin_fallback_note(root, installed_now, why_not))
    return actions


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
