"""The fields that turn the work items in git into a backlog: each status's group (backlog, unstarted, started, completed, cancelled), the `blocked_by` lists and the blocks they form, and the why chain from the mission down to a Spec."""

from __future__ import annotations

import functools
from collections.abc import Callable

from aidd import config
from aidd.workitems import intents

# The work items a delivery team owns and other work waits for, from the rows of schemas/item-types.json.
WORK_TYPES = config.types_with("backlog")


@functools.cache
def _groups() -> dict[str, dict[str, str]]:
    return {t: dict(config.status_table(t)["x-groups"]) for t in config.types_of_form("work_item")}


def group(data: dict, status: str | None = None) -> str | None:
    """The status group of a Spec, Intent, or proposal in `status` (its derived status; the stored one when not
    given); None for another type or an unknown status."""
    item_type = str(data.get("type"))
    default = config.initial_status(item_type) if item_type in WORK_TYPES else None
    return _groups().get(item_type, {}).get(str(status or data.get("status") or default))


def blocked_by(data: dict) -> list[str]:
    """The ids a Spec or an Intent waits for, once each: its `blocked_by`. A value that is no list raises, so the item is set aside as
    unreadable (`work_list._probe`) and never read as the letters of a string."""
    held = data.get("blocked_by") or []
    if not isinstance(held, list):
        raise TypeError(f"blocked_by is a {type(held).__name__}, not a list")
    return list(dict.fromkeys(i for i in held if isinstance(i, str) and i))


def _cycle(edges: dict[str, set[str]]) -> list[str]:
    """One cycle in a directed graph, as the ids along it, or [] when there is none."""
    state: dict[str, int] = {}
    for start in sorted(edges):
        if state.get(start):
            continue
        stack: list[tuple[str, list[str]]] = [(start, sorted(edges.get(start, ())))]
        path = [start]
        state[start] = 1
        while stack:
            node, todo = stack[-1]
            if not todo:
                stack.pop()
                path.pop()
                state[node] = 2
                continue
            nxt = todo.pop(0)
            if state.get(nxt) == 1:
                return path[path.index(nxt) :]
            if not state.get(nxt):
                state[nxt] = 1
                path.append(nxt)
                stack.append((nxt, sorted(edges.get(nxt, ()))))
    return []


def relation_errors(objects: list[tuple[str, dict]]) -> list[str]:
    """A `blocked_by` that points nowhere or at itself, and blocks that form a cycle, a slice line's `blocked_by` among
    them. A slice is a planned Spec, so its id is a target too."""
    where = {str(d["id"]): p for p, d in objects if d.get("type") in WORK_TYPES and d.get("id")}
    lines = intents.slice_lines([d for _, d in objects])
    for sid, (intent, _, _) in lines.items():
        where.setdefault(sid, next((p for p, d in objects if d is intent), ""))
    errs: list[str] = []
    edges: dict[str, set[str]] = {}
    for p, d in objects:
        if d.get("type") not in WORK_TYPES:
            continue
        me = str(d.get("id"))
        try:
            waits = blocked_by(d)
        except TypeError:
            continue  # the schema check names a value that is no list
        for other in waits:
            if other == me:
                errs.append(f"{p}: blocked_by {other} points at itself")
            elif other not in where:
                errs.append(f"{p}: blocked_by {other}: no Spec, Intent, or slice in the Specs folder has that id")
            else:
                edges.setdefault(other, set()).add(me)
    for sid, (_, _, line) in lines.items():
        for other in intents.slice_blocked_by(line):
            if other == sid:
                errs.append(f"{where[sid]}: slice {sid} is blocked_by itself")
            elif other not in where:
                errs.append(f"{where[sid]}: slice {sid} is blocked_by {other}: no Spec, Intent, or slice in the Specs folder has that id")
            else:
                edges.setdefault(other, set()).add(sid)
    cycle = _cycle(edges)
    if cycle:
        errs.append(f"{where[cycle[0]]}: blocks and blocked_by form a cycle ({' -> '.join([*cycle, cycle[0]])}); nothing in it can ever start")
    return errs


def unfinished_blocked_by(data: dict, idx: dict[str, dict], lets_go: Callable[[str], bool]) -> list[str]:
    """The items this one still waits for: its own blocked_by, its slice line's, its parent Intent's (an Intent that
    waits on other work holds every Spec in it), unless `lets_go(id)` (its derived status landed or ended the work). An id
    not in the Specs folder, or a slice with no Spec file, counts as unfinished unless `lets_go` says it merged."""
    me = str(data.get("id"))
    ids = blocked_by(data)
    parent = idx.get(str(data.get("parent") or ""))
    if parent and parent.get("type") == "intent":
        line = intents.slice_lines([parent]).get(me)
        ids += intents.slice_blocked_by(line[2]) if line else []
        ids += blocked_by(parent)
    return [i for i in dict.fromkeys(ids) if not lets_go(i)]
