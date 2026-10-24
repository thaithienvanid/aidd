"""What is past due: a feature flag past its cleanup date, a deprecation past its sunset, a postmortem action, and a
vendor renewal."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Mapping
from pathlib import Path

from aidd.kernel import globs
from aidd.workitems.derived_status import LANDED_STATUSES, spec_status

# The derived status of each Spec, by id, from git (derived_status.Observer); None to read the front matter alone.
Statuses = Mapping[str, str] | None
ENDED = ("cancelled", "rolled_back")


def _status(data: dict, statuses: Statuses) -> str | None:
    """A Spec's status: the one the caller derived, by id, or else what its front matter alone says (the stored status,
    a cache, and draft without one). A Spec the caller did not derive is still in work."""
    return statuses.get(str(data.get("id"))) if statuses is not None else spec_status(data)


def _landed(data: dict, statuses: Statuses) -> bool:
    """Whether a Spec's change has reached the base branch, so its removals and its later dates count."""
    return _status(data, statuses) in LANDED_STATUSES


def _live(objects: list[tuple[str, dict]], statuses: Statuses) -> list[tuple[str, dict]]:
    """The Specs that have not ended: a cancelled or rolled-back Spec's entries never reached anyone."""
    return [(p, d) for p, d in objects if d.get("kind") == "spec" and _status(d, statuses) not in ENDED]


# A kind of entry with a date: the list field, the entry's name key, its date key, and the field of the Spec that removes it.
FLAGS = ("flags", "name", "cleanup_due", "removes_flags")
DEPRECATIONS = ("deprecations", "what", "sunset", "removes_deprecations")


def _latest(specs: list[tuple[str, dict]], kind: tuple[str, str, str, str], statuses: Statuses, landed_only: bool) -> dict:
    """The entry that decides for each name of a kind (FLAGS, DEPRECATIONS): none for a name a landed Spec removes, else
    a landed Spec's entry over one still in work, and the later date of two alike, so a later Spec that declares it
    again extends it once it lands."""
    field, key, due, removes = kind
    removed = {str(n) for _, d in specs if _landed(d, statuses) for n in d.get(removes) or []}
    latest: dict[str, tuple[str, dict, dict]] = {}
    for p, d in specs:
        landed = _landed(d, statuses)
        if landed_only and not landed:
            continue
        for entry in d.get(field) or []:
            if not isinstance(entry, dict) or not entry.get(key) or str(entry[key]) in removed:
                continue
            name, rank = str(entry[key]), (landed, str(entry.get(due, "9999")))
            if name not in latest or rank >= (_landed(latest[name][1], statuses), str(latest[name][2].get(due, "9999"))):
                latest[name] = (p, d, entry)
    return latest


def overdue_flags(objects: list[tuple[str, dict]], today: dt.date, statuses: Statuses = None) -> list[tuple[str, dict, dict]]:
    """(path, Spec, flag) for each `flags` entry whose `cleanup_due` has passed while no landed Spec lists it in
    `removes_flags`; a cancelled or rolled-back Spec's flags never reached users, and a later Spec that declares the same
    flag again with a later `cleanup_due` extends it once it lands. `statuses`: as _status reads them. Cheap: no git."""
    latest = _latest(_live(objects, statuses), FLAGS, statuses, False)
    return [found for found in latest.values() if str(found[2].get("cleanup_due", "9999")) < today.isoformat()]


def deprecation_calendar(objects: list[tuple[str, dict]], statuses: Statuses = None, *, landed_only: bool = False) -> list[tuple[str, dict, dict]]:
    """(path, Spec, deprecation) for each `deprecations` entry no landed Spec lists in `removes_deprecations`, by sunset.
    As with flags, a cancelled or rolled-back Spec's entries never reached consumers, and a later Spec that declares the
    same `what` with a later `sunset` extends it once it lands. `landed_only`: only what landed Specs announced, as a
    client sees it. Cheap: the front matter only, no git."""
    latest = _latest(_live(objects, statuses), DEPRECATIONS, statuses, landed_only)
    return sorted(latest.values(), key=lambda found: (str(found[2].get("sunset", "9999")), str(found[2]["what"])))


def overdue_deprecations(objects: list[tuple[str, dict]], today: dt.date, statuses: Statuses = None) -> list[tuple[str, dict, dict]]:
    """The deprecation calendar's entries whose `sunset` has passed: a warning and a step, never a gate rule."""
    return [found for found in deprecation_calendar(objects, statuses) if str(found[2].get("sunset", "9999")) < today.isoformat()]


def pending_removals(objects: list[tuple[str, dict]], statuses: Statuses, field: str) -> dict[str, list[str]]:
    """For each name a Spec still in work lists in `field` (`removes_flags` or `removes_deprecations`), the ids of those
    Specs: the removal counts once one lands."""
    out: dict[str, list[str]] = {}
    for _, d in _live(objects, statuses):
        if not _landed(d, statuses):
            for name in d.get(field) or []:
                out.setdefault(str(name), []).append(str(d.get("id")))
    return out


def _pending(ids: list[str] | None, field: str) -> str | None:
    if not ids:
        return None
    which = ", ".join(sorted(set(ids)))
    return f"take {which}, which lists it in {field}, through Spec approval and land it: the removal counts once it lands"


def deprecation_removal(dep: dict, pending: list[str] | None = None) -> str:
    """What a deprecation past its sunset asks for, said the same way by `aidd validate`, `aidd list`, and `aidd digest`.
    The value is a JSON string, which YAML reads as the same scalar, whatever quotes it holds."""
    return (
        _pending(pending, "removes_deprecations")
        or f"write the Spec that removes it and lists it in removes_deprecations: [{json.dumps(str(dep.get('what')), ensure_ascii=False)}]"
    )


def deprecation_errors(rel: str, data: dict) -> list[str]:
    """Each deprecation whose `sunset` comes before its `announced`: consumers would lose it before they were told."""
    return [
        f"{rel}: deprecation {dep.get('what')!r} has sunset {dep.get('sunset')} before announced {dep.get('announced')}; "
        "the Sunset date is never earlier than the Deprecation date (RFC 9745), so set the sunset later"
        for dep in data.get("deprecations") or []
        if isinstance(dep, dict) and str(dep.get("sunset", "9999")) < str(dep.get("announced", ""))
    ]


def overdue_actions(rel: str, data: dict, today: dt.date) -> list[str]:
    """Problem management: each action item of a postmortem in review or published whose `due` date has passed and
    that is not `done`. Like the flag cleanup date, a date passing is a warning, never a gate rule."""
    if data.get("status") not in ("in_review", "published"):
        return []
    out = []
    for a in data.get("actions") or []:
        if not isinstance(a, dict) or a.get("done") or str(a.get("due", "9999")) >= today.isoformat():
            continue
        where = f" (tracked in {a['tracked_in']})" if a.get("tracked_in") else ""
        out.append(
            f"{rel}: postmortem {data.get('id')} action {a.get('what')!r} (owner {a.get('owner')}) was due on {a.get('due')} and is not done{where}. "
            "Finish it and record done: true, or have its owner set a new due date"
        )
    return out


def target_errors(rel: str, data: dict) -> list[str]:
    """Each postmortem action whose `target` names no pack or practice skill of aidd-team: the lesson would go nowhere."""
    from aidd import knowledge

    out = []
    for a in data.get("actions") or []:
        if isinstance(a, dict) and a.get("target") and (why := knowledge.target_problem(str(a["target"]))):
            out.append(f"{rel}: postmortem {data.get('id')} action {a.get('what')!r}: {why}")
    return out


def knowledge_action_how(action: dict) -> str:
    """What an open knowledge action asks for, said the same way by `aidd list` and the Learn commands."""
    return (
        f"raise a suggested Spec that updates {action.get('target')}. That change goes to schemas/industry-standards.json or the skill's SKILL.md in "
        "the aidd repository, which a person approves. Record tracked_in, and done: true once it lands"
    )


def flag_cleanup(flag: dict, pending: list[str] | None = None) -> str:
    """What an overdue flag asks for, said the same way by `aidd validate` and `aidd list`."""
    return (
        _pending(pending, "removes_flags")
        or f"write the cleanup Spec that deletes it and lists it in removes_flags: [{json.dumps(str(flag.get('name')), ensure_ascii=False)}]"
    )


# A vendor's renewal comes up in `aidd validate` this many days ahead, so a person decides before it renews by default.
RENEWAL_NOTICE_DAYS = 30


def vendor_renewals(text: str, today: dt.date, notice_days: int = RENEWAL_NOTICE_DAYS) -> list[tuple[str, dt.date, str]]:
    """(vendor, renewal date, owner) for each row of a vendor register's table whose `Renewal date` falls within
    `notice_days` of `today` or has passed. A row without a real date (a placeholder) is skipped."""
    out: list[tuple[str, dt.date, str]] = []
    header: list[str] | None = None
    for line in text.splitlines():
        if not line.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if "renewal date" not in header or set("".join(cells)) <= set("-: "):
            continue
        at = header.index("renewal date")
        try:
            due = dt.date.fromisoformat(cells[at])
        except (IndexError, ValueError):
            continue
        if (due - today).days <= notice_days:
            owner = cells[header.index("owner")] if "owner" in header and header.index("owner") < len(cells) else ""
            out.append((cells[0], due, owner))
    return out


def renewal_warnings(root: Path, objects: list[tuple[str, dict]], today: dt.date, docs_dir: str = "docs") -> list[str]:
    """A warning per vendor whose renewal is near or past, from the repository's vendor register and any other one a
    Spec links."""
    paths = dict.fromkeys(
        [globs.under(docs_dir, "vendors.md")]
        + [
            str(d.get("path"))
            for _, s in objects
            if s.get("kind") == "spec"
            for d in s.get("docs") or []
            if isinstance(d, dict) and d.get("kind") == "vendors" and d.get("path")
        ]
    )
    out = []
    for rel in paths:
        path = root / rel
        if not path.is_file():
            continue
        for vendor, due, owner in vendor_renewals(path.read_text(encoding="utf-8", errors="replace"), today):
            when = f"passed on {due}" if due < today else f"is due on {due}, in {(due - today).days} days"
            out.append(f"{rel}: vendor {vendor}'s renewal {when} (owner {owner or 'not named'}); a person decides to renew, renegotiate, or exit")
    return out
