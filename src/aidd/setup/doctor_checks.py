"""`aidd doctor`: every check of a repository's aidd setup, as (level, message), from the config to the coding agents."""

from __future__ import annotations

import datetime as dt
import json
import os
import shlex
import stat
import sys
from pathlib import Path

from aidd import __version__, config, knowledge, workitems
from aidd.kernel import documents, git, resources, timestamps
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
    """A runbook in use must have been run lately: warn when its tested_on is older than docs.max_runbook_age_days."""
    today = today or dt.date.today()
    max_age = cfg.max_runbook_age_days if cfg else config.MAX_RUNBOOK_AGE_DAYS
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
    docs.max_runbook_age_days (`tested_on`), draft or active, since a backup nobody restored is not yet a backup."""
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


# `aidd doctor` warns this many days before a security.txt `Expires` passes, so a person renews it in time.
SECURITY_TXT_NOTICE_DAYS = 30
SECURITY_TXT = ".well-known/security.txt"


# A security.txt is a few lines; aidd reads no more than this of one.
SECURITY_TXT_MAX_BYTES = 64 * 1024
# An evidence.json names its results, never their logs; aidd reads no more than this of one.
EVIDENCE_MAX_BYTES = 4 * 1024 * 1024


def _regular_file_bytes(root: Path, rel: str, limit: int) -> tuple[bytes | None, str]:
    """At most `limit` + 1 bytes of a regular file inside the repository, or None and why not: "not regular" for a
    symlink, a device, or a file outside the repository, else the OS's error. aidd never follows a link or opens a
    device, which a read could hang on."""
    path = root / rel
    try:
        st = os.lstat(path)
        inside = Path(os.path.realpath(path)).is_relative_to(os.path.realpath(root))
    except OSError as exc:
        return None, str(exc.strerror or exc)
    if not stat.S_ISREG(st.st_mode) or not inside:
        return None, "not regular"
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        return None, str(exc.strerror or exc)
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):  # swapped since the lstat
            return None, "not regular"
        try:
            return f.read(limit + 1), ""
        except OSError as exc:
            return None, str(exc.strerror or exc)


def _security_txt_text(root: Path, rel: str) -> tuple[str | None, str]:
    """The text of a security.txt, or None and why aidd did not read it. aidd opens only a regular file inside the
    repository (`_regular_file_bytes`), and reads at most SECURITY_TXT_MAX_BYTES."""
    data, why = _regular_file_bytes(root, rel, SECURITY_TXT_MAX_BYTES)
    if why == "not regular":
        return None, "it is a symlink or not a regular file, so aidd does not read it; commit the file itself"
    if data is None:
        return None, f"aidd cannot read it ({why}); write it as UTF-8 text"
    if len(data) > SECURITY_TXT_MAX_BYTES:
        return None, f"it is larger than {SECURITY_TXT_MAX_BYTES // 1024} KiB, so aidd does not read it; keep it to the fields RFC 9116 names"
    try:
        return data.decode("utf-8-sig"), ""
    except UnicodeDecodeError:
        return None, "aidd cannot read it, as it is not UTF-8 text; write it as UTF-8 text"


def security_txt_checks(root: Path, cfg: config.Config | None, today: dt.date | None = None) -> list[tuple[str, str]]:
    """With the `cra` target, the repository holds a security.txt (RFC 9116) wherever the site serves it from, any file
    git tracks at `<folder>/.well-known/security.txt`, and each one's `Expires` is more than 30 days away. A file with no
    `Expires`, or one aidd cannot read, warns too."""
    if config.CRA_TARGET not in config.project_compliance(cfg)["targets"]:
        return []
    today = today or dt.date.today()
    tracked = [p for p in git.run(["ls-files", "-z", "--", f":(glob)**/{SECURITY_TXT}"], str(root), check=False).split("\0") if p]
    found = sorted({*tracked, *([SECURITY_TXT] if os.path.lexists(root / SECURITY_TXT) else [])})
    how = "as the vulnerability policy says (`aidd new vulnerability-policy`)"
    if not found:
        return [
            (
                "warn",
                f"project.compliance targets cra and the repository has no {SECURITY_TXT}. Add one (RFC 9116) with Contact and Expires where the site serves it, {how}",
            )
        ]
    out: list[tuple[str, str]] = []
    for rel in found:
        text, problem = _security_txt_text(root, rel)
        if text is None:
            out.append(("warn", f"{rel}: {problem}, {how}"))
            continue
        value = next((line.split(":", 1)[1].strip() for line in text.splitlines() if line.strip().lower().startswith("expires:")), "")
        expires = timestamps.parse_time(value.upper())
        if expires is None:
            out.append(("warn", f"{rel} has no readable Expires (RFC 9116 requires one, such as 2027-06-30T00:00:00Z); add it, less than a year ahead"))
            continue
        left = (expires.date() - today).days
        if left < 0:
            out.append(("warn", f"{rel} expired on {expires.date()}, so finders may not trust its Contact; set Expires again, less than a year ahead"))
        elif left <= SECURITY_TXT_NOTICE_DAYS:
            out.append(
                ("warn", f"{rel} expires on {expires.date()}, in {left} days; a person checks its Contact and sets Expires again, less than a year ahead")
            )
        else:
            out.append(("ok", f"{rel}: expires on {expires.date()}"))
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


def component_lines(cfg: config.Config, root: Path | str = ".") -> list[tuple[str, str]]:
    """Which parts of aidd run here (`components`, `hooks.level`, and the gate's `mode`), and a warning where two of them
    disagree."""
    gate = config.effective_mode(cfg.get("mode"), None, input_trusted=False, fallback=config.profile_mode(cfg.profile))
    parts = [f"{name} {'on' if config.component_on(cfg.raw, name) else 'off'}" for name in config.COMPONENTS]
    shown = ", ".join([f"hooks {config.hook_level(cfg.raw)}", *parts])
    says = (
        "the guard and the gate block what the rules forbid"
        if gate == "enforce"
        else "the guard and the gate advise, and block only a decision an agent makes for a person"
    )
    out = [("ok", f"components: {shown}; {says} (mode: {gate})")]
    if off := workitems.spec_steps_off_note(cfg, str(root)):
        out.append(("info", off))
    if not config.component_on(cfg.raw, "spec_steps") and gate == "enforce":
        out.append(
            (
                "warn",
                "components.spec_steps is false, but the gate blocks: a change on the spec route still needs an approved Spec to merge. "
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
    on_platform = gate.trunk_on_platform(str(root))
    if on_platform and config.effective_mode(cfg.get("mode"), None, input_trusted=False, fallback=config.profile_mode(cfg.profile)) != "enforce":
        out.append(
            (
                "info",
                'a standing approval is on, and the gate only reports (mode: advisory): for a merge only when it passes, set mode: "enforce" '
                "and require `aidd/gate` on the base branch (docs/ADOPTION.md, Hands-off)",
            )
        )
    return out


def worktree_lines(root: Path) -> list[tuple[str, str]]:
    """A warning for each worktree git lists whose folder is gone, one when the default branch is checked out in a
    linked worktree, and a note when merged ones wait to be cleaned."""
    from aidd import workitems

    rows = workitems.worktree_states(str(root))
    out = [("warn", f"worktree {r['path']} is gone from disk: `aidd worktrees clean` prunes it") for r in rows if r["state"] == "missing"]
    trunk = _default_branch_name(str(root))
    main_path = next((r["path"] for r in rows if r["main"]), str(root))
    for r in rows:
        if trunk and not r["main"] and r["state"] != "missing" and r["branch"] == trunk and not _bare(main_path):
            out.append(
                (
                    "info",
                    f"the default branch {trunk} is checked out in the linked worktree {r['path']}, so the root "
                    f"checkout cannot switch to it. To move it back: `git -C {shlex.quote(r['path'])} switch -c <name>`, "
                    f"then `git -C {shlex.quote(main_path)} switch {shlex.quote(trunk)}`",
                )
            )
    merged = [r for r in workitems.cleanable(rows, str(root)) if r["state"] == "merged"]
    if merged:
        out.append(("info", f"{len(merged)} merged worktree(s) can go: `aidd worktrees clean --dry-run` lists them"))
    return out


def _default_branch_name(root: str) -> str:
    """The default branch's name as `aidd land` finds it (`git.default_base`), or "" when there is none."""
    try:
        base = git.default_base(root)
    except git.GitError:
        return ""
    return base.split("/", 1)[1] if base.startswith(("origin/",)) else base


def _bare(path: str) -> bool:
    return git.run(["rev-parse", "--is-bare-repository"], path, check=False).strip() == "true"


def dirty_evidence_lines(root: Path) -> list[tuple[str, str]]:
    """A warning when this branch's latest `aidd test` evidence ran in a dirty tree, which the gate holds as
    `tests.dirty_tree`: the paths it named, and the fix. None for evidence of another branch or none at all."""
    from aidd import gate

    data, _ = _regular_file_bytes(root, f"{config.EVIDENCE_DIR}/evidence.json", EVIDENCE_MAX_BYTES)
    try:
        ev = json.loads(data or b"") if data is not None and len(data) <= EVIDENCE_MAX_BYTES else None
    except (UnicodeDecodeError, ValueError, RecursionError):
        return []
    head = str(ev.get("head_sha") or "") if isinstance(ev, dict) else ""
    sha = len(head) in (40, 64) and set(head) <= set("0123456789abcdef")  # never an option to git
    if not (isinstance(ev, dict) and sha and ev.get("dirty_tree") and git.ok(["merge-base", "--is-ancestor", head, "HEAD"], str(root))):
        return []
    paths = ev.get("dirty_paths")
    # A path is text from a file: each one on one line, with no control character to reach the terminal.
    named = [documents.one_line(p, 200) for p in paths] if isinstance(paths, list) and all(isinstance(p, str) for p in paths) else []
    shown = ", ".join(named[:5]) + (f", and {len(named) - 5} more" if len(named) > 5 else "")
    fix = next(r for r in gate.RULES if r.name == "tests").fix_for("tests.dirty_tree")
    return [("warn", f"the latest `aidd test` here ran in a dirty tree ({shown or 'unnamed paths'}), so the gate holds it as tests.dirty_tree: {fix}")]


def goal_lines(root: Path, cfg: config.Config) -> list[tuple[str, str]]:
    """A warning for each goal branch that lives past limits.max_goal_age_days or falls behind the default branch, and for the
    trunk-based limits on the other branches (workitems.flow_warnings): a long-lived branch drifts, and its merge grows
    hard to review."""
    from aidd import workitems

    limit = workitems.goal_limit(cfg)
    goals = [("warn", w) for g in workitems.goal_branches(str(root)) for w in workitems.goal_warnings(workitems.goal_facts(str(root), g), limit)]
    from aidd import gate

    publish = []
    if workitems.bots_of(cfg) and not gate.agents_publish(str(root)):
        # A bot agent (a cloud agent, a CI agent) works by pushing its branch: only a person publishes here, so it cannot.
        publish.append(
            (
                "warn",
                "identities.bots lists agent accounts, but only a person publishes here (`publish: person`): set `publish: agents` if they push their branches and open PR/MRs",
            )
        )
    return goals + publish + [("warn", w) for w in workitems.flow_warnings(workitems.work_branches(str(root)), cfg, workitems.unpublished_trunk(str(root)))]


def fail_closed_scope(root: Path) -> list[tuple[str, str]]:
    """A warning when AIDD_HOOK_FAIL_CLOSED=1 sits in the user's own Claude Code settings: there it reaches every
    project that uses aidd, and changing it needs a new session. A project fails closed by its own config (the audited
    profile), and an organization by its managed settings."""
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
    `failures_only` (a caller that looks only for a failure, such as `aidd list` and the pane) skips every section
    that only ever warns: the worktrees and branches, the standards, runbooks, and reviews, the pins, and the
    platform's branch protection, which asks GitHub over the network."""
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
        out.extend(component_lines(cfg, root))
        out.extend(fail_closed_scope(root))
        out.extend(standing_rails(root, cfg))
        if not failures_only:
            out.extend(worktree_lines(root))
            out.extend(goal_lines(root, cfg))
            out.extend(dirty_evidence_lines(root))
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
            warn(f"profile {cfg.profile} needs owners.specialists (a security pool at least) before any major change can land")
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
        if not failures_only:
            out.extend(standard_checks(root, cfg))
        for w in knowledge.independent_review_warnings(cfg.get("agents", "models", default={}) or {}, bool(cfg.get("agents", "independent_review"))):
            warn(w)
        for w in knowledge.unknown_key_warnings(cfg.get("agents", "models", default={}) or {}):
            warn(w)
    if not failures_only:
        out.extend(runbook_checks(root, cfg, today=today))
        out.extend(review_checks(root, cfg, today=today))
        out.extend(security_txt_checks(root, cfg, today=today))
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
                say(not missing, wired, f"{label}: the session hooks {', '.join(missing)} are not wired: `aidd init --claude-hooks` adds them")
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
    elif f"aidd@{config.MARKETPLACE}" in config.user_plugins_enabled():
        # The repository shows no Claude Code, but this person's own plugin brings aidd here: say so, and how a teammate gets it.
        out.append(
            (
                "info",
                "Claude Code: your aidd plugin brings the guard, the skill, and the MCP tools here, for you only. "
                "`aidd init --harness claude-code` enables it for the project, so Claude Code offers it to each teammate who trusts the folder",
            )
        )
    if detected and (two := doctor_probes.path_aidd_problem()):
        warn(two)
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

        if not failures_only:  # it only ever warns, and it asks GitHub
            out.extend(platforms.protection_checks(str(root)))
    elif (root / ".gitlab" / "aidd.gitlab-ci.yml").is_file():
        ok("GitLab CI include present; enforce it with a pipeline execution policy")
    elif hook_wiring.local_first(root) and not git.run(["remote"], str(root), check=False).split():
        ok("local-first: no remote and no aidd CI, so `aidd gate` and `aidd land` on this machine are the gate")
    else:
        warn("no aidd CI found; the gate is advisory until CI runs it (with no platform on purpose, `aidd gate` and `aidd land` are the gate)")
    if not failures_only:
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
