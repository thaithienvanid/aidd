"""One step of a view: what to do, who does it, and how, with a stable `code`. next_steps.py and branch_overlaps.py
both build them."""

from __future__ import annotations


def new_step(what: str, who: str, how: str, where: str = "", *, code: str = "") -> dict:
    """One step. `code` names the kind of step (such as `spec.merge_approval`), stable across wording changes."""
    return {"code": code, "where": where, "what": what, "who": who, "how": how}
