"""`aidd doctor`: every check of a repository's aidd setup, as (level, message), from the config to the coding agents."""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

from aidd import __version__, config, knowledge, workitems
from aidd.kernel import documents, git, resources
from aidd.setup import adoption, doctor_probes, hook_wiring, pins


def standard_checks(root: Path, cfg: config.Config) -> list[tuple[str, str]]:
    """Each `standards` entry must name a document that exists, roles the team has, and tests the suite runs. Then
    the copies of library standards and the company's `standards_policy` (standards.doctor_checks)."""

    out: list[tuple[str, str]] = []
    roles = knowledge.roles()["roles"]
    suite = {t.get("name") for t in cfg.get("tests", default=[]) or []}
    for s in cfg.standards:
        name = s["name"]
        if not (root / s["path"]).is_file():
            out.append(("warn", f"standards {name!r}: {s['path']} does not exist, so no agent can read it"))
        unknown = [r for r in s["roles"] if r != "*" and r not in roles]
        if unknown:
            out.append(("warn", f"standards {name!r}: unknown role {', '.join(unknown)}; name aidd-team roles (`aidd owners` lists them) or *"))
        missing = [t for t in s.get("enforced_by", []) if t not in suite]
        if missing:
            out.append(("warn", f"standards {name!r}: enforced_by names no `tests` entry: {', '.join(missing)}; until one runs, the standard is guidance"))
    if cfg.standards and not out:
        enforced = sum(1 for s in cfg.standards if s.get("enforced_by"))
        types = {t: sum(1 for s in cfg.standards if s.get("type", "opinionated") == t) for t in ("opinionated", "industry")}
        kinds = ", ".join(f"{n} {t}" for t, n in types.items() if n)
        out.append(("ok", f"standards: {len(cfg.standards)} ({kinds}), {enforced} enforced by tests; `aidd owners` lists them by role"))
    return out + knowledge.standard_doctor_checks(root, cfg)


def runbook_checks(root: Path, cfg: config.Config | None, today: dt.date | None = None) -> list[tuple[str, str]]:
    """A runbook in use must have been run lately: warn when its tested_on is older than runbook_max_age_days."""
    today = today or dt.date.today()
    max_age = cfg.runbook_max_age_days if cfg else config.RUNBOOK_MAX_AGE_DAYS
    out: list[tuple[str, str]] = []
    for p in workitems.object_files(root, workitems.OPS_DIRS["runbook"]):
        rel = p.relative_to(root).as_posix()
        try:
            data, _ = documents.split_front_matter(p.read_text(encoding="utf-8"), rel)
        except (OSError, UnicodeDecodeError, documents.DocumentError) as exc:
            out.append(("warn", f"{rel}: {exc}"))
            continue
        if data.get("kind") != "runbook" or data.get("status") == "retired":
            continue
        if data.get("restore"):
            out += _restore_drill(rel, data, today, max_age)
            continue
        last = data.get("tested_on")
        if not last:
            if data.get("status") == "active":
                out.append(("warn", f"{rel}: active runbook {data.get('id')} has never been tested; run it in a drill and record tested_on"))
            continue
        try:
            age = (today - dt.date.fromisoformat(str(last))).days
        except ValueError:
            out.append(("warn", f"{rel}: tested_on {last!r} is not a date"))
            continue
        if age > max_age:
            when = f"last tested {last}, {age} days ago (limit {max_age})"
            out.append(("warn", f"{rel}: runbook {data.get('id')} was {when}; run it again and update tested_on"))
    return out


def old_layout(root: Path, cfg: config.Config | None) -> list[tuple[str, str]]:
    """A work item's documents in the folders an earlier aidd used, each with the folder it belongs in now: everything
    about a work item sits beside it, in `specs/<ID>/` (`aidd.workitems.item_folder`). A warning, never a block."""
    docs_dir, specs_dir = (cfg.docs_dir, cfg.specs_dir) if cfg else ("docs", "specs")
    fix = "Move it with `git mv`, then update the paths its work item names (`docs`, `design.files`)"
    moves = [
        (root / docs_dir / "specs", "a work item's documents", lambda name: f"`{specs_dir}/{name}/`, beside the item"),
        (root / docs_dir / "design", "a work item's design files", lambda name: f"`{specs_dir}/{name}/design/`, beside the item"),
        (
            root / docs_dir / "architecture" / "explore",
            "an exploration",
            lambda name: f"`{specs_dir}/<ID>/explore/{name}/`, beside the item it informs, or `{specs_dir}/explore/{name}/`",
        ),
    ]
    out: list[tuple[str, str]] = []
    for base, what, home in moves:
        for folder in sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []:
            if base.name == "design" and not workitems.WORK_ID.fullmatch(folder.name):
                continue  # a project-wide design folder, such as one an index names, is an official doc
            out.append(("warn", f"{folder.relative_to(root).as_posix()}/ holds {what}. Its home is now {home(folder.name)}. {fix}"))
    return out


def review_checks(root: Path, cfg: config.Config | None, today: dt.date | None = None) -> list[tuple[str, str]]:
    """A living doc that records `reviewed_on` in its front matter must have been reviewed lately: warn when the date is
    older than `docs.max_review_age_days`. The living docs are the repository's own (REPO_DOCS) and each doc a Spec
    links with `frozen: false`, except a runbook (runbook_checks reads its `tested_on`). The date is optional."""
    today = today or dt.date.today()
    max_age = cfg.max_review_age_days if cfg else config.MAX_REVIEW_AGE_DAYS
    docs_dir, specs_dir = (cfg.docs_dir, cfg.specs_dir) if cfg else ("docs", "specs")
    paths = [rel.replace("{docs}", docs_dir) for files in workitems.REPO_DOCS.values() for rel, tpl in files if tpl.endswith(".md")]
    for p in workitems.object_files(root, specs_dir):
        try:
            data, _ = documents.split_front_matter(p.read_text(encoding="utf-8"), p.name)
        except (OSError, UnicodeDecodeError, documents.DocumentError):
            continue
        if data.get("kind") == "spec":
            linked = [d for d in data.get("docs") or [] if isinstance(d, dict) and d.get("frozen") is False and d.get("kind") != "runbook"]
            paths += [str(d["path"]) for d in linked if d.get("path")]
    out: list[tuple[str, str]] = []
    for rel in dict.fromkeys(paths):
        p = root / rel
        if not p.is_file() or not p.resolve().is_relative_to(root.resolve()) or not workitems.has_front_matter(p):
            continue
        try:
            data, _ = documents.split_front_matter(p.read_text(encoding="utf-8"), rel)
        except (OSError, UnicodeDecodeError, documents.DocumentError) as exc:
            out.append(("warn", f"{rel}: {exc}"))
            continue
        last = data.get("reviewed_on")
        if not last:
            continue
        try:
            age = (today - dt.date.fromisoformat(str(last))).days
        except ValueError:
            out.append(("warn", f"{rel}: reviewed_on {last!r} is not a date"))
            continue
        if age > max_age:
            out.append(
                (
                    "warn",
                    f"{rel}: last reviewed {last}, {age} days ago (limit {max_age}); a person reviews it, fixes or deletes what is stale, and updates reviewed_on",
                )
            )
    return out


def _restore_drill(rel: str, data: dict, today: dt.date, max_age_days: int) -> list[tuple[str, str]]:
    """A restore runbook (`restore: true`): it states its RTO and RPO, and a person drills the restore within
    runbook_max_age_days (`tested_on`), draft or active, since a backup nobody restored is not yet a backup."""
    rid = data.get("id")
    out: list[tuple[str, str]] = []
    if not (data.get("rto") and data.get("rpo")):
        out.append(("warn", f"{rel}: restore runbook {rid} states no rto and rpo; write the recovery time and recovery point objectives it must meet"))
    last = data.get("tested_on")
    if not last:
        out.append(
            ("warn", f"{rel}: restore runbook {rid} has never had a restore drill; restore from a backup into a scratch environment and record tested_on")
        )
        return out
    try:
        age = (today - dt.date.fromisoformat(str(last))).days
    except ValueError:
        return out + [("warn", f"{rel}: tested_on {last!r} is not a date")]
    if age > max_age_days:
        when = f"last ran {last}, {age} days ago (limit {max_age_days})"
        out.append(("warn", f"{rel}: the restore drill of runbook {rid} {when}; restore from a backup again, check the RTO and RPO held, and update tested_on"))
    return out


def _delegate_check(root: Path, cfg: config.Config) -> tuple[str, str] | None:
    """`agents.delegate: always` with no aidd-team role installed: a fail when the config sets it (the guard denies
    every main-session edit, with no role to hand it to), information when it is the profile's default (no effect)."""

    if config.delegate_mode(cfg.raw) != "always" or config.team_installed(str(root)):
        return None
    if config.delegate_set(cfg.raw):
        return "fail", (
            'agents.delegate: "always", and no aidd-team role is installed: the guard denies every main-session '
            'edit of repository content, with no role to hand it to. Run `aidd init --team` (or install the aidd-team plugin), or set delegate: "auto"'
        )
    return "info", (
        f'agents.delegate: the {cfg.profile} profile starts at "always", which applies only when the team is installed. '
        'Without it, the guard acts as "auto". Run `aidd init --team` to apply it'
    )


def component_lines(cfg: config.Config) -> list[tuple[str, str]]:
    """Which parts of aidd run here (`components`, and the gate's `mode`), and a warning where two of them disagree."""
    gate = config.effective_mode(cfg.get("mode"), None, input_trusted=False)
    shown = ", ".join(f"{name} {'on' if config.component_on(cfg.raw, name) else 'off'}" for name in config.COMPONENTS)
    out = [("ok", f"components: {shown}; the gate {'blocks' if gate == 'enforce' else 'only reports'} (mode: {gate})")]
    if not config.component_on(cfg.raw, "loop") and gate == "enforce":
        out.append(
            (
                "warn",
                "components.loop is false, but the gate blocks: a change on the spec route still needs an approved Spec to merge. "
                'Set mode: "advisory", or turn the loop back on',
            )
        )
    return out


def standing_rails(root: Path, cfg: config.Config) -> list[tuple[str, str]]:
    """Warnings while the person's standing approval is on and nothing else stands behind it: the agent then takes each
    change it covers to the base branch, so the project's own risk rules and a gate that blocks are what still catch a
    path aidd's baseline does not know."""
    from aidd import gate, workitems

    standing = workitems.live_standing_for(cfg, str(root))
    if not standing:
        return []
    out = [("info", f"a standing approval is on ({standing['scope']}), since {standing['since'][:16]}: `stop approving` ends it")]
    if not cfg.get("risk_rules"):
        out.append(
            (
                "warn",
                "a standing approval is on, and the config names no risk_rules of its own: only aidd's baseline raises a risky path to "
                "major. Add the paths that matter here (billing, auth, data) to risk_rules, or approve with `approve all but major`",
            )
        )
    on_platform = gate.platform_of(str(root)) == "preflight"
    if on_platform and config.effective_mode(cfg.get("mode"), None, input_trusted=False) != "enforce":
        out.append(
            (
                "warn",
                'a standing approval is on, and the gate only reports (mode: advisory): set mode: "enforce" and require `aidd/gate` '
                "on the base branch, so a pull request merges only when it passes (docs/ADOPTION.md, Hands-off)",
            )
        )
    return out


def worktree_lines(root: Path) -> list[tuple[str, str]]:
    """A warning for each worktree git lists whose folder is gone, and a note when merged ones wait to be cleaned."""
    from aidd import workitems

    rows = workitems.worktree_states(str(root))
    out = [("warn", f"worktree {r['path']} is gone from disk: `aidd worktrees clean` prunes it") for r in rows if r["state"] == "missing"]
    merged = [r for r in workitems.cleanable(rows, str(root)) if r["state"] == "merged"]
    if merged:
        out.append(("info", f"{len(merged)} merged worktree(s) can go: `aidd worktrees clean --dry-run` lists them"))
    return out


def goal_lines(root: Path, cfg: config.Config) -> list[tuple[str, str]]:
    """A warning for each goal branch that lives past gates.max_goal_days or falls behind the default branch, and for the
    trunk-based limits on the other branches (workitems.flow_warnings): a long-lived branch drifts, and its merge grows
    hard to review."""
    from aidd import workitems

    limit = workitems.goal_limit(cfg)
    goals = [("warn", w) for g in workitems.goal_branches(str(root)) for w in workitems.goal_warnings(workitems.goal_facts(str(root), g), limit)]
    return goals + [("warn", w) for w in workitems.flow_warnings(workitems.work_branches(str(root)), cfg)]


def fail_closed_scope(root: Path) -> list[tuple[str, str]]:
    """A warning when AIDD_HOOK_FAIL_CLOSED=1 sits in the user's own Claude Code settings: there it reaches every
    project that uses aidd, and changing it needs a new session. A project fails closed by its own config (the audited
    profile), and an organization by its managed settings."""
    import json

    user = config.claude_settings_paths(root)[0]
    try:
        env = (json.loads(user.read_text(encoding="utf-8")) or {}).get("env") or {}
    except (OSError, ValueError, AttributeError):
        return []
    if str(env.get("AIDD_HOOK_FAIL_CLOSED", "")) != "1":
        return []
    return [
        (
            "warn",
            f"AIDD_HOOK_FAIL_CLOSED=1 is in your user settings ({user}), so it reaches every project that uses aidd. Remove it: "
            "a project fails closed by its own config (profile: audited), and an organization sets it in its managed settings",
        )
    ]


def doctor(root: Path, *, today: dt.date | None = None, execute: bool = False, failures_only: bool = False) -> list[tuple[str, str]]:
    """Every check of a repository's aidd setup, as (level, message). The coding agents are the ones the repository
    shows (their folders and files), never what this machine has installed; only the aidd plugins' double-load check also
    reads the user's Claude Code settings (`plugins_enabled`). `execute` (the `aidd doctor` command) also
    starts the configured agent hook and MCP server once, with a harmless input, and fails when either cannot run.
    `failures_only` (a caller that looks only for a failure, such as `aidd list`) skips the worktree and branch
    sections, which only ever warn and read git once per branch and worktree."""
    out: list[tuple[str, str]] = []
    ok = lambda m: out.append(("ok", m))  # noqa: E731
    warn = lambda m: out.append(("warn", m))  # noqa: E731
    fail = lambda m: out.append(("fail", m))  # noqa: E731

    def say(good: object, yes: str, no: str) -> None:
        out.append(("ok", yes) if good else ("warn", no))

    ok(f"aidd {__version__}, Python {sys.version.split()[0]}") if sys.version_info >= (3, 11) else fail("Python 3.11+ is required")
    if not (root / ".git").exists():
        warn("not a git repository root")
    cfg = None
    if (root / config.CONFIG_PATH).is_file():
        try:
            cfg = config.load_file(config.CONFIG_PATH, str(root), skip_unread=True)  # an unread URL parent warns
            ok(f"config: profile {cfg.profile}")
            for w in cfg.warnings + config.advice(cfg):
                warn(w)
        except (config.ConfigError, documents.DocumentError, RuntimeError) as exc:
            fail(f"config: {exc}")
    else:
        fail(f"no {config.CONFIG_PATH}; run `aidd init`")
    if cfg:
        out.extend(component_lines(cfg))
        out.extend(fail_closed_scope(root))
        out.extend(standing_rails(root, cfg))
        if not failures_only:
            out.extend(worktree_lines(root))
            out.extend(goal_lines(root, cfg))
        if not cfg.get("tests"):
            warn("no `tests`: every Spec must bring its own commands (characterization)")
        if not cfg.approvers:
            fail(f"profile {cfg.profile} needs owners.approvers; {config.EMPTY_APPROVERS}")
        elif cfg.profile == "solo" and hook_wiring.local_first(root):
            # Solo: the person at this machine is the Approver, and a local approval counts as their git email.
            email = (config.operator_email(root) or "").lower()
            if email and f"email:{email}" not in {config.normalize_identity(a) for a in cfg.approvers}:
                warn(
                    f"local-first: an approval from this machine counts as email:{email}, which owners.approvers ({', '.join(cfg.approvers)}) "
                    f'does not list. So `aidd approve` would record approvals the gate never counts. Add "email:{email}" to owners.approvers'
                )
        if cfg.gates["specialist_approvals"] and not cfg.specialists:
            warn(f"profile {cfg.profile} needs owners.specialists (a security pool at least) before any major change can ship")
        if cfg.gates["separation_of_duties"]:
            # An author never approves their own change: a pool of one person cannot approve that person's major change.
            for pool, who in sorted(cfg.specialists.items()):
                if len(who) == 1 and "/" not in who[0]:
                    warn(
                        f"owners.specialists.{pool} has one member ({who[0]}), who can never approve a change they authored; "
                        "name at least two humans in every specialist pool"
                    )
        if cfg.gates["policy_required_routes"] and not cfg.policy_command:
            fail(
                f"profile {cfg.profile} requires policy.command for {', '.join(cfg.gates['policy_required_routes'])}; "
                "set it (aidd init --policy), or run `AIDD_ORG_PRESET=<preset.yaml> aidd doctor` when the org preset binds it"
            )
        delegate_line = _delegate_check(root, cfg)
        if delegate_line:
            out.append(delegate_line)
        for gate in cfg.get("guard", "held_commands", default=[]) or []:
            until = f", until a person sets {gate['requires']}" if gate.get("requires") else ""
            ok(f"held for a person: `{gate.get('name')}` ({' '.join(gate.get('match', []))}){until}")
        if not (root / cfg.specs_dir).is_dir():
            warn(f"no {cfg.specs_dir}/ directory yet")
        # A team of humans and agents steers by one written goal and reviews by one rubric.
        if cfg.get("goal"):
            ok(f"goal: {cfg.get('goal')}")
        rubric = f"{adoption.REVIEW_POLICY}: the rubric every reviewer follows"
        say(
            (root / adoption.REVIEW_POLICY).is_file(),
            rubric,
            f"no {adoption.REVIEW_POLICY}: the rubric every reviewer, human or agent, follows; `aidd init` writes one",
        )
        out.extend(standard_checks(root, cfg))
        for w in knowledge.independent_review_warnings(cfg.get("agents", "models", default={}) or {}, bool(cfg.get("agents", "independent_review"))):
            warn(w)
        for w in knowledge.unknown_key_warnings(cfg.get("agents", "models", default={}) or {}):
            warn(w)
    out.extend(runbook_checks(root, cfg, today=today))
    out.extend(review_checks(root, cfg, today=today))
    out.extend(old_layout(root, cfg))
    skill = root / adoption.SKILL_REL
    if not (skill / "SKILL.md").is_file():
        warn(f"no vendored skill at {adoption.SKILL_REL}: fine if every agent loads the aidd plugin; otherwise run `aidd init`")
    else:
        bundled = resources.data_dir("skill")
        if skill.resolve() == bundled.resolve():
            ok("skill: this repository is the source")
        else:
            diff = doctor_probes.tree_diff(bundled, skill)
            say(
                not diff, f"skill matches aidd {__version__}", f"skill differs from aidd {__version__}: {', '.join(diff[:5])}; `aidd upgrade --yes` upgrades it"
            )
    for d in adoption.DEFAULT_LINKS if "claude-code" in adoption.detect_harnesses(root) else ():
        link = root / d / "aidd"
        if link.is_symlink() and (link / "SKILL.md").is_file():
            ok(f"{link.relative_to(root)} resolves")
        elif link.is_dir() and (link / "SKILL.md").is_file() and (skill / "SKILL.md").is_file():
            rel = link.relative_to(root)
            say(not doctor_probes.tree_diff(skill, link), f"{rel} is a copy that matches", f"{rel} is a stale copy; `aidd upgrade --yes` refreshes it")
        else:
            warn(f"{Path(d) / 'aidd'} is missing; `aidd init` links it")
    agents = root / "AGENTS.md"
    say(agents.is_file() and "aidd" in agents.read_text(encoding="utf-8"), "AGENTS.md points at the skill", "AGENTS.md does not mention aidd")
    out.extend(instruction_file_size(root))
    detected = adoption.detect_harnesses(root)
    is_source = (skill / "SKILL.md").is_file() and skill.resolve() == resources.data_dir("skill").resolve()
    readers = []  # the agents that need nothing but AGENTS.md: one line for all of them
    for h in detected:
        label = config.HARNESSES[h].label
        if h == "claude-code" and is_source:
            ok(f"{label}: this repository is the plugin source; hooks.json and the plugin manifest carry the hook and the MCP server")
        elif h == "claude-code":
            settings = root / ".claude" / "settings.json"
            plugin = config.plugin_enabled(root)
            out.extend(doctor_probes.claude_wiring_checks(root, execute=execute))
            try:
                hooked = settings.is_file() and hook_wiring.HOOK_COMMAND in settings.read_text(encoding="utf-8")  # every launcher's command ends with it
            except OSError:
                hooked = False
            twice = hook_wiring.session_hooks_wired(settings) if plugin else []
            if twice:
                warn(
                    f"{label}: the aidd plugin is enabled and {settings.relative_to(root)} also wires the session hooks "
                    f"{', '.join(twice)}, so each runs twice; remove those `aidd hook` entries from the settings file"
                )
            elif hooked and not plugin:
                missing = hook_wiring.session_hooks_missing(settings)
                wired = f"{label}: the session hooks ({', '.join(hook_wiring.SESSION_EVENTS)}) are wired"
                say(not missing, wired, f"{label}: the session hooks {', '.join(missing)} are not wired: `aidd init --agent-hooks` adds them")
        elif h == "antigravity":
            out.extend(doctor_probes.antigravity_wiring_checks(root, execute=execute))
            readers.append(label)  # it reads AGENTS.md too
        elif h == "grok-build":
            out.extend(doctor_probes.grok_wiring_checks(root, execute=execute))
            readers.append(label)  # it reads AGENTS.md too
        elif h == "codex":
            out.extend(doctor_probes.codex_wiring_checks(root, execute=execute))
            readers.append(label)  # it reads AGENTS.md too
        elif h == "opencode":
            out.extend(doctor_probes.opencode_wiring_checks(root, execute=execute))
            readers.append(label)  # it reads AGENTS.md too
        elif pointer := config.HARNESSES[h].pointer:
            p = root / pointer
            if p.is_file() and adoption.AGENTS_MARK in p.read_text(encoding="utf-8"):
                ok(f"{label}: {pointer} points at the skill")
            elif config.HARNESSES[h].only_if_present and not p.is_file():
                readers.append(label)
            else:
                warn(f"{label} is in use here, but {pointer} does not point at the skill; `aidd init` writes it")
        else:
            readers.append(label)
    if readers:
        ok(f"{len(readers)} agent{'s' if len(readers) > 1 else ''} read{'' if len(readers) > 1 else 's'} AGENTS.md: {', '.join(readers)}")
    if "claude-code" in detected:
        out.extend(doctor_probes.plugin_double_load(root, config.HARNESSES["claude-code"].label))
    if not detected:
        ok(
            "no coding agent's own files in this repository; AGENTS.md and .agents/skills/ serve any agent that reads them (`aidd init --harness <agent>` wires one)"
        )
    if cfg and cfg.profile == "audited" and "claude-code" in detected:
        managed = doctor_probes.managed_settings_sources()
        say(
            managed,
            f"Claude Code managed settings present ({', '.join(managed)}); `/status` in Claude Code names the one in force",
            "profile audited, but this machine carries no Claude Code managed settings. So each developer's own settings "
            f"decide permissions, the sandbox, and hooks. Deploy aidd's {doctor_probes.MANAGED_SETTINGS_TEMPLATE} through MDM or the admin console "
            "(docs/ENTERPRISE.md). A claude.ai console policy not fetched yet is invisible here: check `/status`",
        )
    wf = root / ".github" / "workflows"
    if (wf / "aidd-gate.yml").is_file() and (wf / "aidd-tests.yml").is_file():
        ok("GitHub workflows present; require the `aidd/gate` status on the protected branch")
        from aidd import platforms  # best effort: says it skipped when offline or without a token

        out.extend(platforms.protection_checks(str(root)))
    elif (root / ".gitlab" / "aidd.gitlab-ci.yml").is_file():
        ok("GitLab CI include present; enforce it with a pipeline execution policy")
    elif hook_wiring.local_first(root) and not git.run(["remote"], str(root), check=False).split():
        ok("local-first: no remote and no aidd CI, so `aidd gate` and `aidd ship` on this machine are the gate")
    else:
        warn("no aidd CI found; the gate is advisory until CI runs it (with no platform on purpose, `aidd gate` and `aidd ship` are the gate)")
    out.extend(pins.pin_checks(root))
    return out


# The agent instruction files load into every session, so they stay about one page. 200 lines is the
# size Anthropic's Claude Code memory guidance targets for a CLAUDE.md (longer files cost context and
# adherence); 12 KiB bounds the same page written in long lines, well under Codex's 32 KiB cap.
INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md")
INSTRUCTION_MAX_LINES = 200
INSTRUCTION_MAX_BYTES = 12 * 1024


def instruction_file_size(root: Path) -> list[tuple[str, str]]:
    """A doctor warning for each agent instruction file past its size, which Learn's corrections grow."""
    out = []
    for name in INSTRUCTION_FILES:
        path = root / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        lines = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
        if lines > INSTRUCTION_MAX_LINES or len(data) > INSTRUCTION_MAX_BYTES:
            limit = f"keep it under {INSTRUCTION_MAX_LINES} lines and {INSTRUCTION_MAX_BYTES // 1024} KiB (about one page)"
            out.append(("warn", f"{name} is {lines} lines, {len(data) // 1024} KiB: {limit}; move detail into skills or docs it links"))
    return out
