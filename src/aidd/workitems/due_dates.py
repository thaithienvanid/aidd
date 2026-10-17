"""What is past due: a feature flag past its cleanup date, a postmortem action, and a vendor renewal."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from aidd.kernel import globs


def overdue_flags(objects: list[tuple[str, dict]], today: dt.date) -> list[tuple[str, dict, dict]]:
    """(path, Spec, flag) for each `flags` entry whose `cleanup_due` has passed while no Spec lists it in
    `removes_flags`; a cancelled or rolled-back Spec's flags never reached users, and a later Spec that declares the same
    flag again with a later `cleanup_due` extends it. Cheap: the front matter only, no git."""
    specs = [(p, d) for p, d in objects if d.get("kind") == "spec" and d.get("status") not in ("cancelled", "rolled_back")]
    removed = {str(n) for _, d in specs for n in d.get("removes_flags") or []}
    latest: dict[str, tuple[str, dict, dict]] = {}
    for p, d in specs:
        for flag in d.get("flags") or []:
            if not isinstance(flag, dict) or not flag.get("name") or str(flag["name"]) in removed:
                continue
            due, name = str(flag.get("cleanup_due", "9999")), str(flag["name"])
            if name not in latest or due >= str(latest[name][2].get("cleanup_due", "9999")):
                latest[name] = (p, d, flag)
    return [found for found in latest.values() if str(found[2].get("cleanup_due", "9999")) < today.isoformat()]


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
        f"raise a suggested Spec that updates {action.get('target')}. That change goes to schemas/roles.json or the skill's SKILL.md in "
        "the aidd repository, which a person approves. Record tracked_in, and done: true once it lands"
    )


def flag_cleanup(flag: dict) -> str:
    """What an overdue flag asks for, said the same way by `aidd validate` and `aidd list`."""
    return f'write the cleanup Spec that deletes it and lists it in removes_flags: ["{flag.get("name")}"]'


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
