"""`aidd doctor`: every check of a repository's aidd setup, as (level, message), from the config to the coding agents."""

from __future__ import annotations

import datetime as dt
import json
import os
import stat
import sys
from pathlib import Path

from aidd import __version__, config, knowledge, risk, workitems
from aidd.kernel import documents, git, resources, timestamps
from aidd.setup import adoption, doctor_probes, pins, upgrading


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
        by_type = ", ".join(f"{n} {t}" for t, n in types.items() if n)
        out.append(("ok", f"standards: {len(cfg.standards)} ({by_type}), {enforced} enforced by tests; `aidd owners` lists them by role"))
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
        if data.get("type") != "runbook" or data.get("status") == "retired":
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
        if data.get("type") == "spec":
            linked = [d for d in data.get("docs") or [] if isinstance(d, dict) and d.get("frozen") is False and d.get("type") != "runbook"]
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


def dirty_evidence_lines(root: Path) -> list[tuple[str, str]]:
    """A warning when this branch's latest `aidd test` evidence ran in a dirty tree: the paths it named, and the fix.
    None for evidence of another branch or none at all."""

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
    return [
        (
            "warn",
            f"the latest `aidd test` here ran in a dirty tree ({shown or 'unnamed paths'}), so its evidence is not for one commit: "
            "commit those paths or add them to .gitignore, then run `aidd test` again",
        )
    ]


def risk_checks(root: Path, cfg: config.Config | None) -> list[tuple[str, str]]:
    """The risk rules in force: each rule names an action, an area, a branch, and a level aidd knows, and each area's
    globs and each action's patterns are usable. A config change a locked rule set aside is said once."""
    out: list[tuple[str, str]] = []
    rs = risk.rule_set(cfg)
    for w in rs.ignored:
        out.append(("warn", w))
    for r in rs.rules:
        known = r.action == "*" or r.action in rs.actions or (r.action.endswith(".*") and any(a.startswith(r.action[:-1]) for a in rs.actions))
        if not known:
            out.append(("warn", f"risks.rules {r.action}: no such action; `aidd risk --list` lists them, and a config adds one under `risks.actions`"))
        if r.area and r.area not in rs.areas:
            out.append(("warn", f"risks.rules {r.action} names the area {r.area!r}, which is not defined; add it under `risks.areas`"))
        if r.role and r.role not in knowledge.roles()["roles"]:
            out.append(("warn", f"risks.rules {r.action} names the role {r.role!r}, which the team does not have"))
    for name, area in rs.areas.items():
        if not area.get("paths"):
            out.append(("warn", f"risks.areas {name}: no paths, so it matches nothing"))
    asks = sum(1 for r in rs.rules if r.level == "ask")
    out.append(("ok", f"risk rules: {len(rs.rules)} in force, {asks} ask; `aidd risk --list` shows each and where it comes from"))
    return out


def _config_quiet(root: Path) -> config.Config | None:
    """The config, or None when there is none or it does not load: another check reports why."""
    try:
        return config.load_file(config.CONFIG_PATH, str(root)) if (root / config.CONFIG_PATH).is_file() else None
    except (config.ConfigError, documents.DocumentError, OSError):
        return None


def harness_checks(root: Path, detected: list[str]) -> list[tuple[str, str]]:
    """Each detected agent's ask rules, against the risk rules in force."""
    out: list[tuple[str, str]] = []
    patterns = risk.harness_patterns(risk.rule_set(_config_quiet(root)), adoption.default_branch(root))
    for h in detected:
        label, fmt = config.HARNESSES[h].label, config.HARNESSES[h].ask_rules
        if not fmt:
            continue
        try:
            done = risk.apply_harness_rules(root, fmt, patterns, write=False)
        except (ValueError, OSError) as exc:
            out.append(("warn", f"{label}: its ask rules cannot be checked ({exc})"))
            continue
        if any(d.startswith("would") for d in done):
            # In aidd's own source an upgrade runs from its code, as `aidd upgrade` itself says there.
            command = upgrading.SOURCE_UPGRADE if upgrading.aidd_source(root) else "aidd upgrade --yes"
            out.append(("warn", f"{label}: its ask rules are not current with the risk rules: `{command}` writes them"))
        else:
            out.append(("ok", f"{label}: its ask rules match the risk rules"))
        out += [("info", f"{label}: {d.removeprefix('kept').strip()}") for d in done if d.startswith("kept")]
        gaps = risk.unwritten(fmt, patterns)
        if gaps:
            out.append(
                (
                    "info",
                    f"{label}: its own rules hold {', '.join(f'`{g}`' for g in gaps)} only in part or not at all (a `*` between words "
                    "is only `origin` and `upstream` there), so the skill asks for the rest",
                )
            )
        wider = sorted(set(risk.widened(fmt, patterns).values()))
        if wider:
            out.append(
                (
                    "info",
                    f"{label}: its own rules hold no `*` inside a command, so they ask before every {', '.join(f'`{w}`' for w in wider)} "
                    "instead: more often than the risk rules, never less",
                )
            )
    others = [config.HARNESSES[h].label for h in detected if not config.HARNESSES[h].ask_rules]
    if others:
        out.append(("info", f"{', '.join(others)}: no ask-rule format aidd writes, so the skill alone says when to ask"))
    return out


def doctor(root: Path, *, today: dt.date | None = None, execute: bool = False, failures_only: bool = False) -> list[tuple[str, str]]:
    """Every check of a repository's aidd setup, as (level, message). The coding agents are the ones the repository
    shows (their folders and files), never what this machine has installed. `execute` (the `aidd doctor` command) also
    starts the configured MCP server once, and fails when it cannot run. `failures_only` skips the sections that only
    ever warn: the standards, runbooks, and reviews, and the pins."""
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
            cfg = config.load_file(config.CONFIG_PATH, str(root))
            ok(f"config: profile {cfg.profile}")
            for w in cfg.warnings:
                if "risks.rules" not in w:
                    warn(w)
        except (config.ConfigError, documents.DocumentError, RuntimeError) as exc:
            fail(f"config: {exc}")
    else:
        fail(f"no {config.CONFIG_PATH}; run `aidd init`")
    out.extend(risk_checks(root, cfg))
    if cfg:
        if not failures_only:
            out.extend(dirty_evidence_lines(root))
        if not cfg.tests:
            warn("no `tests`: every Spec must bring its own commands")
        if not (root / cfg.specs_dir).is_dir():
            warn(f"no {cfg.specs_dir}/ directory yet")
        say(
            (root / adoption.REVIEW_POLICY).is_file(),
            f"{adoption.REVIEW_POLICY}: the rubric every reviewer follows",
            f"no {adoption.REVIEW_POLICY}: the rubric every reviewer, human or agent, follows; `aidd init` writes one",
        )
        if not failures_only:
            out.extend(standard_checks(root, cfg))
        for w in [
            *knowledge.unknown_key_warnings(cfg.get("agents", "models", default={}) or {}),
            *knowledge.unknown_key_warnings(cfg.get("agents", "effort", default={}) or {}, "effort"),
        ]:
            warn(w)
    if not failures_only:
        out.extend(runbook_checks(root, cfg, today=today))
        out.extend(review_checks(root, cfg, today=today))
        out.extend(security_txt_checks(root, cfg, today=today))
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
    detected = adoption.detect_harnesses(root)
    is_source = (skill / "SKILL.md").is_file() and skill.resolve() == resources.data_dir("skill").resolve()
    for d in adoption.DEFAULT_LINKS if "claude-code" in detected and not config.plugin_enabled(root) and not is_source else ():
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
    out.extend(harness_checks(root, detected))
    readers = []
    for h in detected:
        label = config.HARNESSES[h].label
        if h == "claude-code" and not is_source:
            out.extend(doctor_probes.claude_mcp_checks(root, execute=execute))
        elif pointer := config.HARNESSES[h].pointer:
            p = root / pointer
            if p.is_file() and adoption.AGENTS_MARK in p.read_text(encoding="utf-8"):
                ok(f"{label}: {pointer} points at the skill")
            elif config.HARNESSES[h].only_if_present and not p.is_file():
                readers.append(label)
            else:
                warn(f"{label} is in use here, but {pointer} does not point at the skill; `aidd init` writes it")
        elif h != "claude-code":
            readers.append(label)
    if readers:
        ok(f"{len(readers)} agent{'s' if len(readers) > 1 else ''} read{'' if len(readers) > 1 else 's'} AGENTS.md: {', '.join(readers)}")
    if "claude-code" in detected:
        out.extend(doctor_probes.plugin_double_load(root, config.HARNESSES["claude-code"].label))
    elif f"aidd@{config.MARKETPLACE}" in config.user_plugins_enabled():
        out.append(
            (
                "info",
                "Claude Code: your aidd plugin brings the skill and the MCP tools here, for you only. "
                "`aidd init --harness claude-code` enables it for the project and writes its ask rules, so Claude Code offers the plugin "
                "to each teammate who trusts the folder",
            )
        )
    running = config.session_harness(dict(os.environ))
    if running and running not in detected and not (running == "claude-code" and f"aidd@{config.MARKETPLACE}" in config.user_plugins_enabled()):
        out.append(
            (
                "info",
                f"{config.HARNESSES[running].label} runs this session, and this repository does not wire it: it reads only the skill, "
                f"with no ask rules of its own. `aidd init --harness {running}` writes its files and ask rules",
            )
        )
    if not detected:
        ok(
            "no coding agent's own files in this repository; AGENTS.md and .agents/skills/ serve any agent that reads them (`aidd init --harness <agent>` wires one)"
        )
    wf = root / ".github" / "workflows"
    if (wf / "aidd-tests.yml").is_file():
        ok("GitHub: the aidd test workflow is there; make its `tests` check required in the default branch's ruleset, the hard stop")
    elif (root / ".gitlab" / "aidd.gitlab-ci.yml").is_file():
        ok('GitLab: the aidd CI include is there; turn on "Pipelines must succeed" and protect the default branch')
    else:
        out.append(("info", "no aidd CI: `aidd test` runs on this machine; `aidd init --ci github` adds the test workflow"))
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
