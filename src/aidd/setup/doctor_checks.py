"""`aidd doctor`: every check of a repository's aidd setup, as (level, message), from the config to the coding agents."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

from aidd import __version__, config, knowledge, risk, workitems
from aidd.kernel import documents, findings, git, git_reads, index, regular_files, resources, timestamps
from aidd.kernel.regular_files import regular_file_bytes
from aidd.setup import (
    adoption,
    claude_plugins,
    doctor_leftovers,
    doctor_listing,
    doctor_probes,
    doctor_tests,
    domain_packs,
    instruction_imports,
    pins,
    team_install,
)
from aidd.setup.doctor_harnesses import current_rule_formats, harness_checks, no_ask_rules_problem, trust_checks
from aidd.testing import EVIDENCE_MAX_BYTES


def standard_checks(root: Path, cfg: config.Config) -> list[tuple[str, str]]:
    """Each `standards` entry must name a document that exists, roles the team has, and tests the suite runs. Then
    the copies of library standards and the company's `standards_policy` (standards.doctor_checks)."""

    out: list[tuple[str, str]] = []
    roles = knowledge.roles()["roles"]
    suite = {t.get("name") for t in cfg.get("tests", default=[]) or []}
    for s in cfg.standards:
        name = s["name"]
        if not (root / s["path"]).is_file():
            out.append(("warn", f"standards {name!r}: {s['path']} does not exist, so no agent can read it; add the file, or fix its `path` in `standards`"))
        unknown = [r for r in s["roles"] if r != "*" and r not in roles]
        if unknown:
            out.append(("warn", f"standards {name!r}: unknown role {', '.join(unknown)}; name aidd-team roles (`aidd explain --list` lists them) or *"))
        missing = [t for t in s.get("enforced_by", []) if t not in suite]
        if missing:
            out.append(
                (
                    "warn",
                    f"standards {name!r}: enforced_by names no `tests` entry: {', '.join(missing)}; until one runs, the standard is guidance; add that test to `tests`, or drop it from `enforced_by`",
                )
            )
    if cfg.standards and not out:
        enforced = sum(1 for s in cfg.standards if s.get("enforced_by"))
        out.append(("ok", f"standards: {len(cfg.standards)}, {enforced} enforced by tests"))
    return out + knowledge.standard_doctor_checks(root, cfg)


def _unreadable_file(rel: str, exc: Exception) -> str:
    """Why doctor could not read a file, named once: a DocumentError already starts with the path it was given."""
    message = str(exc)
    return message if message.startswith(f"{rel}: ") else f"{rel}: {message}"


def runbook_checks(root: Path, cfg: config.Config | None, today: dt.date | None = None) -> list[tuple[str, str]]:
    """A runbook in use must have been run lately: warn when its tested_on is older than docs.max_runbook_age_days."""
    today = today or dt.date.today()
    max_age = (cfg or config.EMPTY).max_runbook_age_days
    out: list[tuple[str, str]] = []
    for p in workitems.object_files(root, workitems.OPS_DIRS["runbook"]):
        rel = p.relative_to(root).as_posix()
        text, why = workitems.read_document(root, rel)
        try:
            data, _ = documents.split_front_matter(text, rel) if text is not None else ({}, "")
        except documents.DocumentError as exc:
            out.append(("warn", _unreadable_file(rel, exc)))
            continue
        if text is None:
            out.append(("warn", f"{rel}: {why}"))
            continue
        if data.get("type") != "runbook" or data.get("status") == "retired":
            continue
        if "restore" in data and "restores_data" not in data:
            out.append(
                ("warn", f"{rel}: runbook {data.get('id')} holds `restore`, which is now `restores_data`, so its restore drill is not checked: rename it")
            )
        if data.get("restores_data"):
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
            out.append(("warn", f"{rel}: tested_on {last!r} is not a date; write it as YYYY-MM-DD"))
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
    cfg = cfg or config.EMPTY
    max_age = cfg.max_review_age_days
    docs_dir, specs_dir = cfg.docs_dir, cfg.specs_dir
    paths = [rel.replace("{docs}", docs_dir) for files in workitems.REPO_DOCS.values() for rel, tpl in files if tpl.endswith(".md")]
    for p in workitems.object_files(root, specs_dir):
        text, _ = workitems.read_document(root, p.relative_to(root).as_posix())
        try:
            data, _ = documents.split_front_matter(text, p.name) if text is not None else ({}, "")
        except documents.DocumentError:
            continue
        if data.get("type") == "spec":
            linked = [d for d in data.get("docs") or [] if isinstance(d, dict) and d.get("frozen") is False and d.get("type") != "runbook"]
            paths += [str(d["path"]) for d in linked if d.get("path")]
    out: list[tuple[str, str]] = []
    for rel in dict.fromkeys(paths):
        p = root / rel
        if not p.is_file() or not p.resolve().is_relative_to(root.resolve()) or not workitems.has_front_matter(p):
            continue
        text, why = workitems.read_document(root, rel)
        if text is None:
            out.append(("warn", f"{rel}: {why}"))
            continue
        try:
            data, _ = documents.split_front_matter(text, rel)
        except documents.DocumentError as exc:
            out.append(("warn", _unreadable_file(rel, exc)))
            continue
        last = data.get("reviewed_on")
        if not last:
            continue
        try:
            age = (today - dt.date.fromisoformat(str(last))).days
        except ValueError:
            out.append(("warn", f"{rel}: reviewed_on {last!r} is not a date; write it as YYYY-MM-DD"))
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
    """A restore runbook (`restores_data: true`): it states its RTO and RPO, and a person drills the restore within
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
        return out + [("warn", f"{rel}: tested_on {last!r} is not a date; write it as YYYY-MM-DD")]
    if age > max_age_days:
        when = f"last ran {last}, {age} days ago (limit {max_age_days})"
        out.append(("warn", f"{rel}: the restore drill of runbook {rid} {when}; restore from a backup again, check the RTO and RPO held, and update tested_on"))
    return out


# `aidd doctor` warns this many days before a security.txt `Expires` passes, so a person renews it in time.
SECURITY_TXT_NOTICE_DAYS = 30
SECURITY_TXT = ".well-known/security.txt"


# A security.txt is a few lines; aidd reads no more than this of one.
SECURITY_TXT_MAX_BYTES = 64 * 1024


def _security_txt_text(root: Path, rel: str) -> tuple[str | None, str]:
    """The text of a security.txt, or None and why aidd did not read it. aidd opens only a regular file inside the
    repository (`regular_file_bytes`), and reads at most SECURITY_TXT_MAX_BYTES."""
    data, why = regular_file_bytes(root, rel, SECURITY_TXT_MAX_BYTES)
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


RULESET_CHECKS = ("tests", "ci passed")  # the aidd test workflow's job, and the ci workflow's summary job
RULESET_MAX_BYTES = 256 * 1024
_CI_PASSED_JOB = re.compile(r"(?m)^\s*name:\s*[\"']?ci passed[\"']?\s*$")
_TESTS_JOB = re.compile(r"(?m)^(?:  tests:|\s*name:\s*[\"']?tests[\"']?)\s*$")  # the job's id, or its name


def _workflow_defines(root: Path, job_name: re.Pattern[str]) -> bool:
    for path in sorted((root / ".github" / "workflows").glob("*.y*ml")):
        data, _why = regular_file_bytes(root, path.relative_to(root).as_posix(), RULESET_MAX_BYTES)
        if data is not None and job_name.search(data.decode("utf-8", errors="replace")):
            return True
    return False


def ruleset_checks(root: Path) -> list[tuple[str, str]]:
    """Warns when a ruleset file in `.github/rulesets` requires only one of the `tests` and `ci passed` checks while a
    workflow of this repository defines the other, since a change could then merge with that job red. A ruleset that
    requires both, or neither, or a repository that defines only the one it requires, is quiet."""
    out: list[tuple[str, str]] = []
    for path in sorted((root / ".github" / "rulesets").glob("*.json")):
        rel = path.relative_to(root).as_posix()
        data, _why = regular_file_bytes(root, rel, RULESET_MAX_BYTES)
        try:
            ruleset = json.loads(data.decode("utf-8")) if data is not None and len(data) <= RULESET_MAX_BYTES else {}
            rules = [r for r in ruleset.get("rules", []) if isinstance(r, dict) and r.get("type") == "required_status_checks"]
            required = {c.get("context") for r in rules for c in r.get("parameters", {}).get("required_status_checks", []) if isinstance(c, dict)}
        except (ValueError, AttributeError, TypeError):
            continue
        have = [name for name in RULESET_CHECKS if name in required]
        if len(have) != 1:
            continue
        missing = next(name for name in RULESET_CHECKS if name not in have)
        if _workflow_defines(root, _TESTS_JOB if missing == "tests" else _CI_PASSED_JOB):
            out.append(
                (
                    "warn",
                    f"{rel} requires the `{have[0]}` check but not `{missing}`. A workflow here defines `{missing}`, so a change can merge while that job is red: "
                    "add it to required_status_checks in the file, then import the ruleset again in Settings, Rules, Rulesets",
                )
            )
    return out


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

    data, _ = regular_file_bytes(root, f"{config.EVIDENCE_DIR}/evidence.json", EVIDENCE_MAX_BYTES)
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


def index_lines(root: Path) -> list[tuple[str, str]]:
    """A warning when aidd never opens the index in the git folder (`index.refusal`), naming the file and the next step."""
    try:
        path = workitems.index_path(root)
        why = index.refusal(path.parent.parent, path)
    except git.GitError:
        return []
    head = why.partition(":")[0]
    fix = "remove the link" if " is a link" in head else "remove it"
    return [("warn", f"index: {head}, so aidd answers from the files without it, which loses nothing; {fix}, and aidd rebuilds the index")] if why else []


def risk_checks(root: Path, cfg: config.Config | None) -> list[tuple[str, str]]:
    """The risk rules in force: each rule names an action, an area, a branch, and a level aidd knows, and each area's
    globs and each action's patterns are usable. A config change a locked rule set aside is said once."""
    out: list[tuple[str, str]] = []
    rs = risk.rule_set(cfg)
    for w in rs.ignored:
        out.append(("warn", w))
    for line in risk.lock_effects(rs):
        out.append(("info", line))
    for r in rs.rules:
        if r.area and r.area not in rs.areas:
            out.append(("warn", f"risks.rules {r.action} names the area {r.area!r}, which is not defined; add it under `risks.areas`"))
        if r.role and r.role not in knowledge.roles()["roles"]:
            out.append(("warn", f"risks.rules {r.action} names the role {r.role!r}, which the team does not have; `aidd explain --list` lists the roles"))
    for name, area in rs.areas.items():
        if not area.get("paths"):
            out.append(("warn", f"risks.areas {name}: no paths, so it matches nothing; add `paths` under it, or remove the area"))
    asks = sum(1 for r in rs.rules if r.level == "ask")
    out.append(("ok", f"risk rules: {len(rs.rules)} in force, {asks} ask; `aidd risk --list` shows each and where it comes from"))
    return out


def doctor_findings(results: list[tuple[str, str]]) -> list[dict]:
    """One finding for each check of `doctor` that failed or warned, with its message as the check gives it, in the check's
    order. A check that passed, or only informs, is no finding."""
    return [
        findings.finding("doctor.check_failed", message) if result == "fail" else findings.finding("doctor.check_warned", message)
        for result, message in results
        if result in ("fail", "warn")
    ]


def doctor(root: Path, *, today: dt.date | None = None, execute: bool = False, failures_only: bool = False) -> list[tuple[str, str]]:
    """Every check of a repository's aidd setup, as (level, message). The coding agents are the ones the repository
    shows (their folders and files), never what this machine has installed. `execute` (the `aidd doctor` command) also
    starts the configured MCP server once, and fails when it cannot run, and asks an installed OpenCode its version.
    `failures_only` skips the sections that only ever warn: the standards, runbooks, and reviews, and the pins. It
    writes nothing, so each ref read runs once (`git_reads.shared_reads`)."""
    with git_reads.shared_reads(), team_install.rendered_once():
        return _doctor(root, today=today, execute=execute, failures_only=failures_only)


def _notes(root: Path, cfg: config.Config | None) -> list[tuple[str, str]]:
    """The lines a full run adds and `--failures-only` leaves out: what a run left open, versions of aidd that differ, names
    aidd retired in files that load, evidence written on a dirty tree, and the narrowed form a test command could take."""
    out = doctor_leftovers.leftover_lines(root)
    out.extend(doctor_probes.version_lines(root))
    if cfg:
        out.extend(doctor_probes.retired_name_lines(root))
        out.extend(dirty_evidence_lines(root))
        if cfg.tests:
            out.extend(doctor_tests.related_tests_lines(cfg))
    return out


def _doctor(root: Path, *, today: dt.date | None, execute: bool, failures_only: bool) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    ok = lambda m: out.append(("ok", m))  # noqa: E731
    warn = lambda m: out.append(("warn", m))  # noqa: E731
    fail = lambda m: out.append(("fail", m))  # noqa: E731

    def say(good: object, yes: str, no: str) -> None:
        out.append(("ok", yes) if good else ("warn", no))

    ok(f"aidd {__version__}, Python {sys.version.split()[0]}") if sys.version_info >= (3, 11) else fail("Python 3.11+ is required")
    if not (root / ".git").exists():
        warn("this folder is not a git repository: run `git init` here, or run `aidd doctor` inside the repository")
    cfg = None
    broken = False
    if (root / config.CONFIG_PATH).is_file():
        try:
            cfg = config.load_file(config.CONFIG_PATH, str(root))
            ok(f"config: profile {cfg.profile}")
            for w in cfg.warnings:
                if "risks.rules" not in w:
                    warn(w)
        except (config.ConfigError, documents.DocumentError, RuntimeError) as exc:
            # First, so the problem is what a person reads first: every command that decides stops until the config loads.
            out.insert(0, ("fail", f"config: {exc}. Fix what it names, then run `aidd validate`; every command that decides stops until it loads"))
            broken = True
    else:
        fail(f"no {config.CONFIG_PATH}; run `aidd init`")
    if broken:
        warn(
            "risk rules: not checked, because the config above does not load, and the built-in rules alone are not the rules in force; fix the config, then run `aidd doctor` again"
        )
    else:
        out.extend(risk_checks(root, cfg))
    from aidd.setup import delegation_wiring, doctor_environments

    out.extend(doctor_environments.environment_checks(root, cfg))
    out.extend(delegation_wiring.doctor_lines(root, cfg, today))
    out.extend(index_lines(root))
    if not failures_only:
        out.extend(_notes(root, cfg))
    if cfg:
        if not cfg.tests:
            warn("no `tests`: every Spec must bring its own commands; add a `tests` entry to .aidd/config.yaml for the project's own")
        if not (root / cfg.specs_dir).is_dir():
            warn(f'no {cfg.specs_dir}/ directory yet; `aidd new spec "<title>"` creates it with the first Spec')
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
            *knowledge.unknown_key_warnings(cfg.get("agents", "max_turns", default={}) or {}, "max_turns"),
        ]:
            warn(w)
    if not failures_only:
        out.extend(runbook_checks(root, cfg, today=today))
        out.extend(review_checks(root, cfg, today=today))
        out.extend(security_txt_checks(root, cfg, today=today))
        out.extend(domain_packs.doctor_lines(root))
        out.extend(doctor_listing.listing_lines(root))
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
    detected = adoption.wired_harnesses(root)
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
    say(
        "aidd" in (regular_files.repository_text(root, "AGENTS.md") or ""),
        "AGENTS.md points at the skill",
        "AGENTS.md does not mention aidd; `aidd init` appends the pointer, keeping your config",
    )
    out.extend(instruction_file_size(root))
    if broken:
        warn("each agent's ask rules: not compared with the risk rules, because the config above does not load")
    else:
        out.extend(harness_checks(root, detected))
    if "opencode" in detected and execute and (why := doctor_probes.opencode_version_problem(root)):
        warn(why)
    out.extend(trust_checks(detected))
    out.extend(doctor_probes.launcher_checks())
    readers = []
    for h in detected:
        label = config.HARNESSES[h].label
        if h == "claude-code" and not is_source:
            out.extend(doctor_probes.claude_mcp_checks(root, execute=execute))
        if config.HARNESSES[h].imports:
            if why := instruction_imports.problem(root, config.HARNESSES[h]):
                warn(why)
            elif instruction_imports.hiders_present(root, config.HARNESSES[h]):
                ok(f"{label}: {config.HARNESSES[h].pointer} imports AGENTS.md, which {label} skips otherwise")
            else:
                readers.append(label)
        elif pointer := config.HARNESSES[h].pointer:
            p = root / pointer
            if adoption.AGENTS_MARK in (regular_files.repository_text(root, pointer) or ""):
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
        out.append(
            (
                "info",
                "Claude Code: your aidd plugin brings the skill and the MCP tools here, for you only. "
                "`aidd init --harness claude-code` enables it for the project and writes its ask rules, so Claude Code offers the plugin "
                "to each teammate who trusts the folder",
            )
        )
    running = config.session_harness(dict(os.environ))
    # Decided from the rules on disk, never from detection alone: VS Code's ask rules for Copilot leave no Copilot signal.
    # A detected agent that takes ask rules and has none gets harness_checks' own warning instead.
    if broken:
        pass
    elif not current_rule_formats(root) and not any(config.HARNESSES[h].ask_rules for h in detected):
        out.append(("warn", no_ask_rules_problem(running, detected)))
    elif running and running not in detected and not (running == "claude-code" and f"aidd@{config.MARKETPLACE}" in config.user_plugins_enabled()):
        out.append(
            (
                "info",
                f"{config.HARNESSES[running].label} runs this session, and this repository does not wire it: it reads only the skill, "
                f"with no ask rules of its own. `aidd init --harness {running}` writes its files and ask rules",
            )
        )
    wf = root / ".github" / "workflows"
    if (wf / "aidd-tests.yml").is_file():
        ok(
            "GitHub: the aidd test workflow is there; make its `tests` check required in the default branch's ruleset, the hard stop. It holds a change to the "
            'tests of the commit it forked from, so the ruleset aidd writes also turns on "Require branches to be up to date before merging", which holds it to the newest. Where many changes merge at once, use a merge queue instead'
        )
    elif (root / ".gitlab" / "aidd.gitlab-ci.yml").is_file():
        ok(
            'GitLab: the aidd CI include is there; turn on "Pipelines must succeed" and protect the default branch. The check holds a change to the tests of the '
            "commit it forked from, so also use the fast-forward merge method, which needs an up-to-date branch, to hold it to the newest"
        )
    else:
        out.append(("info", "no aidd CI: `aidd test` runs on this machine; `aidd init --ci github` adds the test workflow"))
    if not failures_only:
        out.extend(ruleset_checks(root))
        out.extend(pins.pin_checks(root))
        out.extend(claude_plugins.channel_checks(root))
    return out


# The agent instruction files load into every session, so they stay about one page. 200 lines is the
# size Anthropic's Claude Code memory guidance targets for a CLAUDE.md (longer files cost context and
# adherence). 12 KiB bounds the same page written in long lines: about half of Antigravity's 24,000-byte cut for one rule
# file, and well under Codex's 32 KiB for the whole chain of files (config.SIZES holds both, with the pages).
INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md")
INSTRUCTION_MAX_LINES = 200
INSTRUCTION_MAX_BYTES = 12 * 1024


def instruction_file_size(root: Path) -> list[tuple[str, str]]:
    """A doctor warning for each agent instruction file past its size, which Learn's corrections grow."""
    out = []
    for name in INSTRUCTION_FILES:
        data, _ = regular_files.regular_file_bytes(root, name, INSTRUCTION_MAX_BYTES)
        if data is None:
            continue  # missing, or a link or a pipe, which aidd never reads
        lines = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
        if lines > INSTRUCTION_MAX_LINES or len(data) > INSTRUCTION_MAX_BYTES:
            size, more = os.lstat(root / name).st_size, " or more" if len(data) > INSTRUCTION_MAX_BYTES else ""
            limit = f"keep it under {INSTRUCTION_MAX_LINES} lines and {INSTRUCTION_MAX_BYTES // 1024} KiB (about one page)"
            out.append(("warn", f"{name} is {lines} lines{more}, {size // 1024} KiB: {limit}; move detail into skills or docs it links"))
    return out
