"""The standards registry checked against its evidence: each standard with its dates and what proves it, the ones past
their review, and the ones due soon."""

from __future__ import annotations

import datetime as dt

from aidd.knowledge import role_text, team_registry


def dated_entries() -> list[dict]:
    """Every dated entry the team applies: standards by role, by domain pack, and by practice skill, extensions, and the
    practice skills themselves, with `where` naming its owner."""
    data = team_registry.roles()
    out = []
    for key in data["order"]:
        out += [dict(s, where=f"role {key}") for s in data["roles"][key]["standards"]]
        out += [dict(s, where=f"extension {key}") for s in data["roles"][key].get("extends", [])]
    for d in data["domains"]:
        out += [dict(s, where=f"domain {d['slug']}") for s in d["standards"]]
    for name in role_text.practice_names():
        out += [dict(s, where=f"practice {name}") for s in data.get("practices", {}).get(name, {}).get("standards", [])]
        # The skill's own date says when its text was last re-read; the editions it names are checked above, one entry
        # each, so its date is a review, never a source check, and a rewrite of many skills in a day is no bulk edit.
        front = role_text.practice_front(name)
        out.append({"name": f"practice skill aidd-team:{name}", "reviewed": front["checked"], "where": f"practice {name}"})
    return out


def dated_on(s: dict) -> str:
    """An entry's date: `checked` against a source, or `reviewed` for a practice with no source to check."""
    return str(s.get("checked") or s.get("reviewed") or "")


def stale_standards(today: dt.date, max_days: int | None = None) -> list[dict]:
    """Entries due for review, each with `age_days` and `why`: older than their cadence (`review_every_days`, else 90
    days for an emerging entry and 365 for an established one; `max_days`, when a caller passes it, for every entry), dated in
    the future or not at all, or past their `review_due`."""
    from aidd.knowledge import upkeep

    stale = []
    for s in dated_entries():
        limit = max_days if max_days is not None else upkeep.cadence_days(s)
        try:
            age = (today - dt.date.fromisoformat(dated_on(s))).days
        except (ValueError, TypeError):
            stale.append(dict(s, age_days=limit + 1, why="no valid date"))
            continue
        due = str(s.get("review_due") or "")
        if age < 0:
            stale.append(dict(s, age_days=age, why="dated in the future"))
        elif age > limit:
            stale.append(dict(s, age_days=age, why=f"older than its {limit}-day review cadence"))
        elif due and due < today.isoformat():
            stale.append(dict(s, age_days=age, why=f"its review_due {due} has passed"))
    return sorted(stale, key=lambda s: -s["age_days"])


def due_soon(today: dt.date, days: int = 90) -> list[dict]:
    """Entries not yet stale that come due for review within `days`, once each, soonest first, each with `due_on`."""
    from aidd.knowledge import upkeep

    stale = {str(s.get("id") or s.get("name")) for s in stale_standards(today)}
    seen: set[str] = set()
    out = []
    for s in dated_entries():
        key = str(s.get("id") or s.get("name"))
        if key in seen or key in stale:
            continue
        seen.add(key)
        try:
            due = dt.date.fromisoformat(dated_on(s)) + dt.timedelta(days=upkeep.cadence_days(s))
        except (ValueError, TypeError):
            continue
        if s.get("review_due"):
            due = min(due, dt.date.fromisoformat(str(s["review_due"])))
        if due <= today + dt.timedelta(days=days):
            out.append(dict(s, due_on=due.isoformat()))
    return sorted(out, key=lambda s: s["due_on"])
