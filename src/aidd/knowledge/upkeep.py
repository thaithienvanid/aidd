"""When the team's knowledge is due again, and where a lesson goes.

- The review cadence: an entry is due `review_every_days` after its date, else 90 days for an emerging entry and 365
  for an established one; a dated obligation also carries `review_due`. A change to it is a change to
  schemas/roles.json, a protected path that a person approves.
- A postmortem action may `target` a pack or a skill (`pack:<slug>`, `skill:<name>`): the lesson belongs in the team's
  knowledge, and `aidd list` shows it until it is done.
"""

from __future__ import annotations

import hashlib

from aidd.knowledge import role_text, team_registry

REVIEW_EVERY_DAYS = team_registry.REVIEW_EVERY_DAYS  # one table for the registry and the library (team_registry)


def spread(key: str, cadence: int) -> int:
    """The default cadence less a stable offset of up to a quarter of it, from the entry's id: entries checked on the
    same day come due across the last quarter of their window, never all on one day. The same id always gets the same
    offset, on every machine."""
    span = max(cadence // 4, 1)
    return cadence - int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16) % span


def cadence_days(s: dict) -> int:
    """Days between reviews of an entry: its own `review_every_days`, else the default for its maturity, spread by its
    id (spread)."""
    own = s.get("review_every_days")
    if own:
        return int(own)
    default = REVIEW_EVERY_DAYS.get(str(s.get("maturity") or "established"), REVIEW_EVERY_DAYS["established"])
    return spread(str(s.get("id") or s.get("name") or ""), default)


def target_problem(target: str) -> str | None:
    """Why a postmortem action's `target` names nothing the team knows, or None."""
    kind, _, name = str(target).partition(":")
    if kind == "pack":
        known = [d["slug"] for d in team_registry.roles()["domains"]]
        return None if name in known else f"target {target} names no pack; the packs are {', '.join(sorted(known))}"
    if kind == "skill":
        known = role_text.practice_names()
        return None if name in known else f"target {target} names no practice skill; the skills are {', '.join(sorted(known))}"
    return f"target {target} is neither pack:<slug> nor skill:<name>"


def open_actions(data: dict) -> list[dict]:
    """A postmortem's actions that target a pack or a skill and are not done, once it is in review or published."""
    if data.get("kind") != "postmortem" or data.get("status") not in ("in_review", "published"):
        return []
    return [a for a in data.get("actions") or [] if isinstance(a, dict) and a.get("target") and not a.get("done")]
