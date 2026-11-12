"""The product scope against the Intents, as `aidd status` shows it: which items no Intent carries, and how many Intents are in
flight. Nothing here is stored. The map is a view of the files, so it is never stale and never committed.

A product outcome, or a requirement when only a BRD exists, or a standing outcome, is stalled while it is active and no Intent
that serves it is approved, active, or done with its result still to come. A stalled item is the agent's next step: it proposes
the smallest Intents that serve it, for a person to approve.
"""

from __future__ import annotations

from collections.abc import Mapping

from aidd.workitems import criteria, product_scope, status
from aidd.workitems.product_scope import ACTIVE, Item, ProductScope

# An Intent as the map reads it: its derived status and its front matter, by id.
Intents = Mapping[str, tuple[str, dict]]


def carries(state: str, data: dict) -> bool:
    """Whether an Intent carries the item it serves: it is approved or active, or it is done and its results are still to come."""
    return state in status.INTENT_IN_FLIGHT or (state == "done" and not criteria.measured(data))


def carried_types(scope: ProductScope) -> tuple[str, ...]:
    """The types of item an Intent serves in this product scope: outcomes with a PRD or standing outcomes, else requirements."""
    return ("outcome",) if {"prd", "standing-outcomes"} & set(scope.files) else ("requirement",)


def serving(intents: Intents, item_id: str) -> list[str]:
    """The ids of the Intents that serve `item_id`, in id order."""
    return [i for i, (_, data) in intents.items() if data.get("serves") == item_id]


def stalled(scope: ProductScope, intents: Intents) -> list[Item]:
    """The active items that no Intent carries, in the order the files list them. A product scope that did not read whole
    has none, because a file left out could hold the item that carries them."""
    types = carried_types(scope)
    if not scope.exists or not scope.whole:
        return []
    return [i for i in scope.items.values() if i.type in types and i.status == ACTIVE and not any(carries(*intents[n]) for n in serving(intents, i.id))]


def uncovered(scope: ProductScope) -> list[Item]:
    """The active requirements of the BRD that no active outcome of the PRD serves: a person adds the outcome, so it is no step of an
    agent's. A requirement the PRD holds beside a BRD is to move into the BRD, so it is not asked for."""
    if "prd" not in scope.files or "brd" not in scope.files or not scope.whole:
        return []
    served = {i.serves for i in scope.items.values() if i.type == "outcome" and i.status == ACTIVE}
    return [i for i in scope.items.values() if i.type == "requirement" and i.file_type == "brd" and i.status == ACTIVE and i.id not in served]


def in_flight(intents: Intents) -> int:
    """How many Intents are approved or active."""
    return sum(1 for state, _ in intents.values() if state in status.INTENT_IN_FLIGHT)


def max_in_flight(scope: ProductScope) -> int | None:
    """The most Intents approved or active at once, from the intent order; None for no limit."""
    order = scope.files.get(product_scope.ORDER)
    limit = order.data.get("max_in_flight") if order is not None and order.readable else None
    return limit if isinstance(limit, int) and not isinstance(limit, bool) else None


def ended(state: str) -> bool:
    """Whether an Intent is closed: done or cancelled."""
    return state in status.INTENT_ENDED
