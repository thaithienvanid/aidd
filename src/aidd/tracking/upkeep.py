"""`aidd list --upkeep`: the upkeep that is due, from what aidd already knows. It reads the repository's files (and the
event files given), never the network, and decides nothing: each item names the command or skill that takes it, and a
person decides what to do.

- `upkeep.standard_review`: a copy of a library standard (`aidd standard add`) past its review cadence or its
  `review_due`; in aidd's own repository, a registry entry past its cadence too
- `upkeep.flag_cleanup`: a feature flag past its `cleanup_due`, with no Spec that lists it in `removes_flags`
- `upkeep.deprecation_removal`: a deprecation past its `sunset`, with no Spec that lists it in `removes_deprecations`
- `upkeep.backfill_due`: an emergency change whose backfill Spec and post-incident review are still open
- `upkeep.flaky_test`: a test over the flaky limit in the gate events given (`--events`)
- `upkeep.waiver_expiring`: a waiver in `project` that ends within WAIVER_NOTICE_DAYS, or has ended
- `upkeep.runbook_stale`: a runbook past its `tested_on` limit, or never tested
- `upkeep.doctor_warning`: any other warning or failure of `aidd doctor` (without running the hook or the MCP server)
- `upkeep.config_unread`: a config it cannot read, or a URL parent in `extends` it did not fetch (it reads offline)
"""

from __future__ import annotations

import contextlib
import datetime as dt
import os
from pathlib import Path

from aidd import config
from aidd.kernel import documents, timestamps

# A waiver shows here this many days before it ends: `aidd validate` warns 14 days ahead, upkeep plans earlier.
WAIVER_NOTICE_DAYS = 30

# Where each kind of item goes. A route names a team command or a practice skill, or the person who decides.
ROUTES = {
    "upkeep.standard_review": ("standards-update", "read the source again and update the standard (CONTRIBUTING.md, Update a standard)"),
    "upkeep.flag_cleanup": ("release-rollout", "/aidd-team:specify writes the cleanup Spec, with the aidd-team:release-rollout skill"),
    "upkeep.deprecation_removal": ("api-design", "/aidd-team:specify writes the removal Spec, with the aidd-team:api-design skill"),
    "upkeep.backfill_due": ("postmortem", "/aidd-team:postmortem, then the backfill Spec through Spec approval"),
    "upkeep.flaky_test": ("flaky-quarantine", "a person quarantines it; a later change fixes it (/aidd-team:fix)"),
    "upkeep.waiver_expiring": ("waiver", "meet the rule (a Spec, or /aidd-team:fix), or a person approves a new waiver"),
    "upkeep.runbook_stale": ("runbook-drill", "run the runbook in a drill and record tested_on (the SRE prepares it; a person runs it)"),
    "upkeep.doctor_warning": ("doctor", "`aidd doctor` names the fix"),
    "upkeep.config_unread": ("doctor", "`aidd validate` online, or name the parent by path in `extends`"),
}


def _item(code: str, what: str, where: str | None = None, due: str | None = None) -> dict:
    route, how = ROUTES[code]
    return {"code": code, "what": what, "where": where, "due": due, "route": route, "how": how}


def _front(path: Path, rel: str) -> dict | None:
    try:
        return documents.split_front_matter(path.read_text(encoding="utf-8"), rel)[0]
    except (OSError, UnicodeDecodeError, documents.DocumentError):
        return None


def standard_reviews(root: Path, cfg: config.Config, today: dt.date) -> list[dict]:
    """Copies of library standards past their review cadence or `review_due`; in aidd's own repository (which holds
    schemas/roles.json and src/aidd/), the registry entries `aidd eval standards` names too."""
    from aidd import knowledge

    out = []
    for e in knowledge.standard_copies(cfg.standards):
        rel = str(e.get("path") or "")
        data = _front(root / rel, rel) if rel else None
        if data is None:
            continue
        sid = e["from_library"]["id"]
        cadence = knowledge.LIBRARY_REVIEW_EVERY_DAYS.get(str(data.get("maturity")), knowledge.LIBRARY_REVIEW_EVERY_DAYS["established"])
        reviewed, due = timestamps.parse_date(data.get("reviewed")), timestamps.parse_date(data.get("review_due"))
        dates = [d for d in (reviewed + dt.timedelta(days=cadence) if reviewed else None, due) if d]
        next_review = min(dates) if dates else None
        if next_review is not None and next_review < today:
            out.append(_item("upkeep.standard_review", f"the library standard {sid} was due for review on {next_review}", rel, next_review.isoformat()))
    if (root / "schemas" / "roles.json").is_file() and (root / "src" / "aidd").is_dir():
        from aidd import knowledge

        for s in knowledge.stale_standards(today):
            name = s.get("name") or s.get("id") or "an entry"
            out.append(_item("upkeep.standard_review", f"{name} ({s['where']}): {s['why']}", "schemas/industry-standards.json"))
        # A library pin held back while a release waits out its cooldown, now free to move (library_checks.cooldown_findings).
        for line in knowledge.ended_cooldowns(today=today):
            sid = line.split(":", 1)[0]
            out.append(_item("upkeep.standard_review", f"the library standard {line}", f"standards/{sid}.md"))
    return out


def _objects(root: Path, cfg: config.Config) -> list[tuple[str, dict]]:
    folder = root / cfg.specs_dir
    found = []
    for p in sorted(folder.rglob("*.md")) if folder.is_dir() else []:
        rel = p.relative_to(root).as_posix()
        if (data := _front(p, rel)) is not None:
            found.append((rel, data))
    return found


def statuses(root: Path, cfg: config.Config, objects: list[tuple[str, dict]]) -> dict[str, str] | None:
    """The derived status of each Spec, by id, as `aidd list` shows it, so a removal counts once its Spec has landed;
    None when git cannot answer, and the front matter alone decides."""
    from aidd import workitems
    from aidd.kernel import git

    try:
        texts = [(rel, data, (root / rel).read_text(encoding="utf-8", errors="replace")) for rel, data in objects]
        return workitems.Observer(root, cfg).working_tree(cfg.specs_dir, texts) if texts else {}
    except (OSError, git.GitError):
        return None


def flag_cleanups(objects: list[tuple[str, dict]], today: dt.date, statuses: dict[str, str] | None = None) -> list[dict]:
    from aidd import workitems

    return [
        _item(
            "upkeep.flag_cleanup",
            f"{data.get('id')}'s flag {flag.get('name')} was due for removal on {flag.get('cleanup_due')}",
            rel,
            str(flag.get("cleanup_due")),
        )
        for rel, data, flag in workitems.overdue_flags(objects, today, statuses)
    ]


def deprecation_sunsets(objects: list[tuple[str, dict]], today: dt.date, statuses: dict[str, str] | None = None) -> list[dict]:
    from aidd import workitems

    return [
        _item(
            "upkeep.deprecation_removal",
            f"{data.get('id')}'s deprecation {dep.get('what')} passed its sunset on {dep.get('sunset')}",
            rel,
            str(dep.get("sunset")),
        )
        for rel, data, dep in workitems.overdue_deprecations(objects, today, statuses)
    ]


def backfills(objects: list[tuple[str, dict]]) -> list[dict]:
    """Emergency changes whose backfill Spec and post-incident review are still open: no `outcome.learn_ref` yet."""
    from aidd import workitems

    out = []
    for rel, data in objects:
        if data.get("kind", "spec") != "spec" or data.get("route") != "emergency" or (data.get("outcome") or {}).get("learn_ref"):
            continue
        if workitems.spec_status(data) in ("cancelled", "rolled_back"):
            continue
        due = (data.get("emergency") or {}).get("review_due")
        backfill = (data.get("emergency") or {}).get("backfill")
        what = (
            f"{data.get('id')}'s backfill" + (f" ({backfill})" if backfill else "") + " and post-incident review" + (f" are due {due}" if due else " are open")
        )
        out.append(_item("upkeep.backfill_due", what, rel, str(due) if due else None))
    return out


def flaky_tests(event_files: list[str]) -> list[dict]:
    from aidd.tracking import metrics

    if not event_files:
        return []
    found = metrics.flaky(metrics.load_events(event_files))
    return [
        _item("upkeep.flaky_test", f"{t['name']} passed on a re-run after failing on {t['passed_on_rerun']} of {t['heads']} heads, over the limit")
        for t in found["tests"]
        if t["over_limit"]
    ]


def waivers(cfg: config.Config, today: dt.date) -> list[dict]:
    out = []
    for w in (cfg.get("project", "waivers", default=[]) or []) if cfg else []:
        until = timestamps.parse_date(w.get("until"))
        if until is None or (until - today).days > WAIVER_NOTICE_DAYS:
            continue
        state_ = "ended" if until < today else "ends"
        out.append(_item("upkeep.waiver_expiring", f"the waiver of rule {w.get('rule')!r} {state_} on {until}", config.CONFIG_PATH, until.isoformat()))
    return out


def setup_checks(root: Path, cfg: config.Config, today: dt.date) -> list[dict]:
    """The runbooks past their drill, then every other warning or failure `aidd doctor` reports (it runs nothing)."""
    from aidd import setup

    runbooks = [m for level, m in setup.runbook_checks(root, cfg, today) if level == "warn"]
    out = [_item("upkeep.runbook_stale", m, m.split(":", 1)[0]) for m in runbooks]
    with _offline():  # upkeep reads files only: doctor's online checks say they skipped
        checks = setup.doctor(root, today=today)
    out += [_item("upkeep.doctor_warning", f"{level}: {m}") for level, m in checks if level in ("warn", "fail") and m not in runbooks]
    return out


@contextlib.contextmanager
def _offline():
    """AIDD_OFFLINE=1 for the length of the block, then the environment as it was: upkeep reads files only, so no
    `extends` URL parent is fetched and doctor's online checks say they skipped."""
    before = os.environ.get("AIDD_OFFLINE")
    os.environ["AIDD_OFFLINE"] = "1"
    try:
        yield
    finally:
        if before is None:
            os.environ.pop("AIDD_OFFLINE", None)
        else:
            os.environ["AIDD_OFFLINE"] = before


def upkeep_items(root: Path, *, events: list[str] | None = None, today: dt.date | None = None) -> list[dict]:
    """Every upkeep item that is due, in a fixed order by kind, each kind in path order. A config it cannot read offline
    (a URL parent, say) is an item of its own, with the items that need no config."""
    today = today or dt.date.today()
    with _offline():
        try:
            cfg = config.load_file(config.CONFIG_PATH, str(root), skip_unread=True)
        except (OSError, config.ConfigError, documents.DocumentError, RuntimeError, ValueError) as exc:
            first = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
            what = f"the aidd config cannot be read offline: {first}"
            return [_item("upkeep.config_unread", what, config.CONFIG_PATH), *flaky_tests(list(events or []))]
        objects = _objects(root, cfg)
        derived = statuses(root, cfg, objects)
        return [
            *[_item("upkeep.config_unread", w, config.CONFIG_PATH) for w in cfg.warnings if config.UNREAD_PARENT in w],
            *standard_reviews(root, cfg, today),
            *flag_cleanups(objects, today, derived),
            *deprecation_sunsets(objects, today, derived),
            *backfills(objects),
            *flaky_tests(list(events or [])),
            *waivers(cfg, today),
            *setup_checks(root, cfg, today),
        ]


def upkeep_markdown(found: list[dict]) -> str:
    if not found:
        return "No upkeep is due.\n"
    lines = ["| Upkeep | Where | Due | Route |", "| --- | --- | --- | --- |"]
    lines += [f"| {i['what']} | {i['where'] or ''} | {i['due'] or ''} | {i['how']} |" for i in found]
    return "\n".join(lines) + "\n"
