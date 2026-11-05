"""`aidd doctor`: every check of a repository's aidd setup, as (level, message), from the config to the coding agents."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from collections.abc import Iterable
from pathlib import Path

from aidd import __version__, config, knowledge, risk, workitems
from aidd.kernel import documents, git, resources, text, timestamps
from aidd.kernel.regular_files import regular_file_bytes
from aidd.setup import adoption, claude_plugins, doctor_probes, marked_sections, pins, unread_state, upgrading
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


def _unreadable_file(rel: str, exc: Exception) -> str:
    """Why doctor could not read a file, named once: a DocumentError already starts with the path it was given."""
    message = str(exc)
    return message if message.startswith(f"{rel}: ") else f"{rel}: {message}"


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
            out.append(("warn", _unreadable_file(rel, exc)))
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
            out.append(("warn", _unreadable_file(rel, exc)))
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


def no_ask_rules_problem(running: str | None, detected: list[str]) -> str:
    """The warning when aidd wrote no ask rules here, so no agent stops at an ask by itself. It names the detected
    agents that take none, where the skill and branch protection are the stops, and the command that writes the rules
    for the agent of this session, else for each agent aidd writes them for, if the person also uses one."""
    keys = text.series([h.key for h in config.ask_rule_harnesses()], "or")
    none_take = [config.HARNESSES[h].label for h in detected if not config.HARNESSES[h].ask_rules]
    if none_take:
        why = f"{text.series(none_take, 'and')} take{'s' if len(none_take) == 1 else ''} no ask rules"
    else:
        why = "no coding agent this repository wires takes them"
    stops = "so the skill and the default branch's protection are the stops here"
    if running and config.HARNESSES[running].ask_rules:
        how = f"`aidd init --harness {running}` writes them for {config.HARNESSES[running].label}, which runs this session"
    elif none_take:
        how = f"if you also use {keys}, `aidd init --harness <key>` writes its ask rules"
    else:
        how = f"`aidd init --harness <key>` writes them for {keys}"
    return f"no ask rules: {why}, {stops}. {how[0].upper() + how[1:]}"


def current_rule_formats(root: Path) -> list[str]:
    """The harness formats whose ask rules are on disk and current: listed in `.aidd/harness-rules.json`, and with
    nothing `apply_harness_rules` would still write. A ledger whose file a person removed counts for nothing."""
    patterns = risk.harness_patterns(risk.rule_set(_config_quiet(root)), adoption.push_rule_branches(root))
    out = []
    for fmt in risk.written_formats(root):
        try:
            done = risk.apply_harness_rules(root, fmt, patterns, write=False)
        except (ValueError, OSError):
            continue
        if not any(d.startswith("would") for d in done):
            out.append(fmt)
    return out


def _stale_rules_warning(root: Path, label: str) -> str:
    """Why an agent's ask rules lag the risk rules, and the command that writes them. When git cannot tell the default
    branch, each new local branch makes them stale again, so the way to name it comes first."""
    # In aidd's own source an upgrade runs from its code, as `aidd upgrade` itself says there.
    command = upgrading.SOURCE_UPGRADE if upgrading.aidd_source(root) else "aidd upgrade --yes"
    if git.default_branches(str(root))[1]:
        return f"{label}: its ask rules are not current with the risk rules: `{command}` writes them"
    return (
        f"{label}: its ask rules are not current with the risk rules, and git cannot tell the default branch, so each new branch makes them "
        f"stale again. Run `git config init.defaultBranch <branch>`, then `{command}`"
    )


def harness_checks(root: Path, detected: list[str]) -> list[tuple[str, str]]:
    """Each detected agent's ask rules, against the risk rules in force."""
    out: list[tuple[str, str]] = []
    rs = risk.rule_set(_config_quiet(root))
    patterns, read_paths = risk.harness_patterns(rs, adoption.push_rule_branches(root)), risk.harness_read_paths(rs)
    for h in detected:
        label, fmt = config.HARNESSES[h].label, config.HARNESSES[h].ask_rules
        if not fmt:
            continue
        try:
            done = risk.apply_harness_rules(root, fmt, patterns, read_paths=read_paths, write=False)
        except (ValueError, OSError) as exc:
            out.append(("warn", f"{label}: its ask rules cannot be checked ({exc})"))
            continue
        if any(d.startswith("would") for d in done):
            out.append(("warn", _stale_rules_warning(root, label)))
        else:
            out.append(("ok", f"{label}: its ask rules match the risk rules"))
        out += [("info", f"{label}: {d.removeprefix('kept').strip()}") for d in done if d.startswith("kept")]
        out += [("warn", f"{label}: {w}") for w in (risk.opencode_shadow_warnings(root, patterns) if fmt == "opencode" else [])]
        gaps = risk.unwritten(fmt, patterns)
        # A `gh api` write has a pattern for each flag order, which a leading-words format cannot hold: one short line says so.
        api = [g for g in gaps if g.startswith("gh api")]
        # Intent agreement has no prompt there at all, which a person must know plainly: the skill alone asks for it.
        agreement = [g for g in gaps if g in (rs.actions.get("intent.agree") or {}).get("commands", [])]
        out += _agreement_notes(label, rs, bool(agreement))
        told = api + agreement
        listed = [f"`{g}`" for g in gaps if g not in told]
        if api:
            out.append(
                (
                    "info",
                    f"{label}: `gh api` writes (a merge, a ref move, a release, a branch protection change) get no prompt from its rules, so the skill asks. "
                    "`gh pr merge` and `gh release create` keep their prompt.",
                )
            )
        if listed:
            out.append(
                ("info", f"{label}: its own prompts miss a few forms of {_gap_actions(rs, [g for g in gaps if g not in told])}, so the skill asks for those")
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
    return out + harness_closing_notes(root, detected)


def _agreement_notes(label: str, rs, no_prompt: bool) -> list[tuple[str, str]]:
    """What a person must know about `intent.agree` in one agent: it has no prompt there (`no_prompt`), or its prompt reads the
    command text, which a heredoc, `-F <file>`, or `-m "$MSG"` hides the trailer from. The skill asks, and `aidd status` reads the trailer."""
    if no_prompt:
        return [("info", f"{label}: no prompt for `intent.agree`, so the skill asks first, and `aidd status` reads the `Agreed-by` trailer")]
    if not (rs.actions.get("intent.agree") or {}).get("commands"):
        return []
    hidden = 'a message written as a heredoc, with `-F <file>`, or as `-m "$MSG"`'
    return [
        (
            "info",
            f"{label}: its prompt for `intent.agree` reads the command text, so {hidden} hides the `Agreed-by` trailer from it: the skill asks first, and `aidd status` reads the trailer",
        )
    ]


def harness_closing_notes(root: Path, detected: list[str]) -> list[tuple[str, str]]:
    """The notes after each agent's own lines: the branches the push rules guard when git cannot tell the default branch,
    and the agents aidd writes no ask rules for."""
    out: list[tuple[str, str]] = []
    if any(config.HARNESSES[h].ask_rules for h in detected) and not git.default_branches(str(root))[1]:
        out.append(("info", adoption.default_branch_note(adoption.push_rule_branches(root))))
    others = [config.HARNESSES[h].label for h in detected if not config.HARNESSES[h].ask_rules]
    if others:
        out.append(("info", f"{', '.join(others)}: no ask-rule format aidd writes, so the skill alone says when to ask"))
    return out


def _gap_actions(rs, gaps: list[str]) -> str:
    """The actions whose command patterns a harness's own rules cannot hold, each beside what it does, such as
    `git.branch.delete` (Delete a branch, here or on a remote): what the gap means for the person, never the pattern."""
    named: dict[str, str] = {}
    for gap in gaps:
        owners = [a for a, spec in rs.actions.items() if gap in (spec.get("commands") or [])] or (["git.push"] if gap.startswith("git push") else [])
        named.update({a: str(rs.actions.get(a, {}).get("description") or "").rstrip(".") for a in owners})
    return text.series([f"`{a}` ({what})" if what else f"`{a}`" for a, what in named.items()], "and") or "a few commands"


def repeats_trust_step(how: str, check: str) -> bool:
    """Whether the way to check the trust starts as the trust step does, so saying it again adds nothing."""
    return check.split(",", 1)[0].strip() == how.split(" and ", 1)[0].strip()


def trust_checks(detected: list[str]) -> list[tuple[str, str]]:
    """For each detected agent with a trust step (`config.Trust`): whether its ask rules wait for the person to trust the
    folder, what else it holds back until then, how to check, and the words to type. The trust lives in the person's own
    files outside the repository, which aidd never reads, so each line says aidd cannot see it."""
    out: list[tuple[str, str]] = []
    for h in detected:
        label, trust = config.HARNESSES[h].label, config.HARNESSES[h].trust
        if trust is None:
            continue
        when = f"{trust.when}, " if trust.when else ""
        check = "" if repeats_trust_step(trust.how, trust.check) else f"; {trust.check}"
        asks = f"{when}its ask rules hold only once you trust this folder" if trust.holds_ask_rules else "its ask rules hold here now"
        line = f"{label}: {asks}. Until you trust the folder, it holds back {trust.holds}. To trust it, {trust.how}. aidd cannot see whether you have{check}"
        out.append(("info", line))
    return out


def doctor(root: Path, *, today: dt.date | None = None, execute: bool = False, failures_only: bool = False) -> list[tuple[str, str]]:
    """Every check of a repository's aidd setup, as (level, message). The coding agents are the ones the repository
    shows (their folders and files), never what this machine has installed. `execute` (the `aidd doctor` command) also
    starts the configured MCP server once, and fails when it cannot run, and asks an installed OpenCode its version.
    `failures_only` skips the sections that only ever warn: the standards, runbooks, and reviews, and the pins. It
    writes nothing, so each ref read runs once (`git.shared_reads`)."""
    with git.shared_reads():
        return _doctor(root, today=today, execute=execute, failures_only=failures_only)


def _doctor(root: Path, *, today: dt.date | None, execute: bool, failures_only: bool) -> list[tuple[str, str]]:
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
    from aidd.setup import delegation_wiring

    out.extend(delegation_wiring.doctor_lines(root, cfg))
    if not failures_only:
        out.extend(unread_state.unread_state(root))
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
    if "opencode" in detected and execute and (why := doctor_probes.opencode_version_problem(root)):
        warn(why)
    out.extend(trust_checks(detected))
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
    # Decided from the rules on disk, never from detection alone: VS Code's ask rules for Copilot leave no Copilot signal.
    # A detected agent that takes ask rules and has none gets harness_checks' own warning instead.
    if not current_rule_formats(root) and not any(config.HARNESSES[h].ask_rules for h in detected):
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
        ok("GitHub: the aidd test workflow is there; make its `tests` check required in the default branch's ruleset, the hard stop")
    elif (root / ".gitlab" / "aidd.gitlab-ci.yml").is_file():
        ok('GitLab: the aidd CI include is there; turn on "Pipelines must succeed" and protect the default branch')
    else:
        out.append(("info", "no aidd CI: `aidd test` runs on this machine; `aidd init --ci github` adds the test workflow"))
    if not failures_only:
        out.extend(ruleset_checks(root))
        out.extend(pins.pin_checks(root))
        out.extend(claude_plugins.channel_checks(root))
    return out


_CITED_COMMAND = re.compile(r"`aidd ([a-z][a-z-]*)")


def removed_command_checks(root: Path, commands: Iterable[str]) -> list[tuple[str, str]]:
    """A warning for each instruction file with a section of aidd's, in any of its marks, that cites a command (such as
    `aidd gate`) not among `commands`, the ones this aidd has. An agent that follows it runs a command that fails."""
    known = set(commands)
    out = []
    for path in upgrading.instruction_files(root):
        text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
        spans = [s for mark in (adoption.AGENTS_MARK, config.TEAM_MARK) for s in marked_sections.sections(text, mark)]
        gone = sorted({c for s in spans for c in _CITED_COMMAND.findall(text[s.start : s.end])} - known)
        if gone:
            names = ", ".join(f"`aidd {c}`" for c in gone)
            out.append(
                (
                    "warn",
                    f"{path.relative_to(root).as_posix()}: the text between aidd's marks names {names}, which this aidd does not have, "
                    "so an agent that follows it fails. Run `aidd upgrade --yes` to refresh that text; your own text stays. "
                    "If upgrade says it left the section alone, delete that section and run `aidd init`",
                )
            )
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
