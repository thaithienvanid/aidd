"""The fields that turn the work items in git into a backlog: each status's group (backlog, unstarted, started, completed, cancelled), the typed relations and the blocks they form, and the why chain from the mission down to a Spec."""

from __future__ import annotations

import functools
from collections.abc import Callable

from aidd import config
from aidd.kernel import resources
from aidd.workitems import intents

GROUPS = ("backlog", "unstarted", "started", "completed", "cancelled")
WORK_TYPES = ("spec", "intent")


@functools.cache
def _groups() -> dict[str, dict[str, str]]:
    common = resources.load_json("common.schema.json")["$defs"]
    return {
        "spec": dict(common["status"]["x-groups"]),
        "intent": dict(common["intent_status"]["x-groups"]),
        "proposal": dict(resources.load_json("proposal.schema.json")["properties"]["status"]["x-groups"]),
    }


def group(data: dict, status: str | None = None) -> str | None:
    """The status group of a Spec, Intent, or proposal in `status` (its derived status; the stored one when not
    given); None for another type or an unknown status."""
    item_type = str(data.get("type"))
    default = "draft" if item_type in WORK_TYPES else None
    return _groups().get(item_type, {}).get(str(status or data.get("status") or default))


def is_duplicate(data: dict) -> bool:
    """This item repeats another (`duplicates`), which carries the work."""
    return any(r["type"] == "duplicates" for r in relations(data))


def relations(data: dict) -> list[dict]:
    return [r for r in data.get("relations") or [] if isinstance(r, dict) and r.get("type") and r.get("id")]


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
    """Relations that point nowhere or at themselves, and blocks that form a cycle, a slice line's `blocked_by` among
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
        for relation, other in [(r["type"], str(r["id"])) for r in relations(d)]:
            if other == me:
                errs.append(f"{p}: {relation} {other} points at itself")
            elif other not in where:
                errs.append(f"{p}: {relation} {other}: no Spec, Intent, or slice in the Specs folder has that id")
            elif relation == "blocks":
                edges.setdefault(me, set()).add(other)
            elif relation == "blocked_by":
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


def waiting_on(data: dict, idx: dict[str, dict], lets_go: Callable[[str], bool]) -> list[str]:
    """The items this one still waits for: its own blocked_by, its slice line's, its parent Intent's (an Intent that
    waits on other work holds every Spec in it), and every item that says it blocks this one, unless `lets_go(id)` (its
    derived status landed or ended the work) or it is a duplicate. An id not in the Specs folder, or a slice with no
    Spec file, counts as unfinished unless `lets_go` says it merged."""
    me = str(data.get("id"))
    ids = [str(r["id"]) for r in relations(data) if r["type"] == "blocked_by"]
    parent = idx.get(str(data.get("parent") or ""))
    if parent and parent.get("type") == "intent":
        line = intents.slice_lines([parent]).get(me)
        ids += intents.slice_blocked_by(line[2]) if line else []
        ids += [str(r["id"]) for r in relations(parent) if r["type"] == "blocked_by"]
    ids += [oid for oid, other in idx.items() if oid != me and any(r["type"] == "blocks" and str(r["id"]) == me for r in relations(other))]
    return [i for i in dict.fromkeys(ids) if not lets_go(i) and not (i in idx and is_duplicate(idx[i]))]


def why(data: dict, idx: dict[str, dict], cfg: config.Config | None, progress: dict[str, tuple[int, int]] | None = None) -> list[dict]:
    """Why this Spec matters, widest first: its Intent (with `progress`, its children finished of all, as "n/m"), and
    its own hypothesis (or, once measured, its outcome). Each link is {type, id?, text, progress?}; a link with nothing
    written is left out."""
    chain: list[dict] = []
    parents: list[dict] = []
    seen: set[str] = set()
    parent = data.get("parent")
    while parent and str(parent) not in seen and len(parents) < 8:
        seen.add(str(parent))
        found = idx.get(str(parent))
        if found is None:
            parents.append({"type": "parent", "id": str(parent), "text": "not in the Specs folder"})
            break
        link = {"type": found.get("type"), "id": str(parent), "text": str(found.get("goal") or found.get("title") or "")}
        if progress and str(parent) in progress:
            link["progress"] = "{}/{}".format(*progress[str(parent)])
        parents.append(link)
        parent = found.get("parent")
    chain += reversed(parents)
    result = (data.get("outcome") or {}).get("result")
    if data.get("hypothesis") or result:
        text = str(data.get("hypothesis") or "")
        if result:
            text = f"{text} (outcome: {result})" if text else f"outcome: {result}"
        chain.append({"type": "spec", "id": str(data.get("id")), "text": text})
    return chain
