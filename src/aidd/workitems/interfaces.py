"""Interface consumers: the interfaces a Spec `provides` and `consumes`, by stable name, and who to tell when a provider is revised.

Advice only. Nothing here blocks a revision: `aidd status` names the open Specs that consume a revised Spec's interfaces,
so the question to the person names them and their owners hear first, and `aidd validate` warns about an interface nobody
provides. A Spec is open until it is done, rolled back, or cancelled.
"""

from __future__ import annotations

from collections.abc import Mapping

from aidd.workitems import status


def interface_names(data: dict, key: str) -> list[str]:
    """The interface names a Spec lists under `provides` or `consumes`, once each, in order."""
    raw = data.get(key)
    return [n for n in dict.fromkeys(str(x) for x in raw if isinstance(x, str) and x)] if isinstance(raw, list) else []


def consumer_note(provider: dict, specs: Mapping[str, dict], states: Mapping[str, str]) -> str:
    """For a provider that was revised, the open Specs consuming each interface it provides, with their owners:
    "orders-api: SPEC-7 (alice), SPEC-9 (payments-team)", one clause per interface, joined by "; ". Empty when the
    Spec was never revised, provides nothing, or nobody open consumes it."""
    if not provider.get("revisions"):
        return ""
    me = str(provider.get("id"))
    clauses = []
    for name in interface_names(provider, "provides"):
        who = [
            f"{sid} ({other.get('owner') or other.get('owner_team') or 'no owner'})"
            for sid, other in specs.items()
            if sid != me and name in interface_names(other, "consumes") and states.get(sid, "draft") not in status.TERMINAL
        ]
        if who:
            clauses.append(f"{name}: {', '.join(who)}")
    return "; ".join(clauses)


def unprovided_warnings(objects: list[tuple[str, dict]]) -> list[str]:
    """A warning for each interface a Spec consumes that no Spec in the repository provides."""
    specs = [(p, d) for p, d in objects if d.get("type") == "spec"]
    provided = {n for _, d in specs for n in interface_names(d, "provides")}
    return [
        f"{p}: consumes {n}, but no Spec provides it; name it in the provider's `provides`, or fix the name (fine if the provider lives outside the repository)"
        for p, d in specs
        for n in interface_names(d, "consumes")
        if n not in provided
    ]
