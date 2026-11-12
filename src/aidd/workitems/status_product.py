"""`aidd status product`: the product scope as a view of its files and the Intents. The map is derived on each run, so it is
never stale and never committed (schemas/product-status.schema.json).

It shows what each file waits for, the items with the Intents that serve them, the open Intents in the order of the intent
order and then the closed ones with their result, the items no Intent carries, and the Intents in flight against the limit.
"""

from __future__ import annotations

from pathlib import Path

from aidd import config
from aidd.kernel import documents, findings
from aidd.workitems import current_work, ids, product_approval, product_checks, product_map, product_scope, status, work_list
from aidd.workitems.product_scope import ProductFile

# The word that stands for the product scope where `aidd status` takes an id or a path.
PRODUCT_TARGET = "product"
# What each file of the product scope says about its approval, as `files[].state` gives it.
APPROVED, CHANGED, NOT_APPROVED, UNREADABLE = "approved", "changed", "not_approved", "unreadable"
SHAPES = {
    ("brd", "prd"): "a BRD and a PRD",
    ("prd",): "a PRD",
    ("brd",): "a BRD",
    ("standing-outcomes",): "standing outcomes",
}
NOTHING = (
    "There is no product scope yet. `aidd new prd` writes the PRD, `aidd new brd` the BRD, and `aidd new standing-outcomes` the standing outcomes, "
    "each for a person to fill in and approve"
)


def _approval(root: Path, f: ProductFile) -> tuple[str, str]:
    """The state of one file's approval, and what changed since it: UNREADABLE when it did not read, NOT_APPROVED when no yes
    stands as git records it, CHANGED when the file differs from the version the person approved, else APPROVED."""
    if not f.readable:
        return UNREADABLE, ""
    found = product_approval.approved_text(root, f.path, f.data)
    if found is None:
        return NOT_APPROVED, ""
    changed = product_checks.changes_since(found[0], found[1], f.data, f.body)
    return (CHANGED, "; ".join(changed)) if changed else (APPROVED, "")


def _decider(cfg: config.Config | None, f: ProductFile) -> str:
    """Who answers for a file: the sponsor of a BRD, the product owner of the order, else the config's first approver."""
    named = f.data.get(product_checks.DECIDERS.get(f.type, ""))
    return str(named) if isinstance(named, str) and status.PLACEHOLDER not in named else next(iter((cfg or config.EMPTY).approvers), "")


def _file_row(root: Path, cfg: config.Config | None, f: ProductFile) -> dict:
    state, what = _approval(root, f)
    row: dict = {"type": f.type, "path": f.path, "state": state}
    if state in (APPROVED, CHANGED):
        row |= {"approved_by": f.data["approved_by"], "approved_at": f.data["approved_at"]}
    if state == CHANGED:
        row["changed"] = what
    if state in (NOT_APPROVED, CHANGED):
        row["next"] = work_list.spoken(work_list.step_of_code("product_scope.approve"), "", person=_decider(cfg, f))
    return row


def _intent_row(item: dict, data: dict) -> dict:
    """One Intent as the map shows it: its status, what it serves, who owns it, what it waits for, its progress, and its criteria."""
    row = {k: item[k] for k in ("id", "title", "status", "path") if k in item}
    row |= {k: data[k] for k in ("serves", "owner") if isinstance(data.get(k), str)}
    row |= {k: item[k] for k in ("blocked_by", "progress", "criteria") if k in item}
    return row


def _intents(answer: dict, found: list[tuple[str, dict]], order: list[str]) -> list[dict]:
    """The Intents of the open work: the open ones first, in the order of the intent order (the rest by id), then the closed."""
    data = {str(d.get("id")): d for _, d in found if d.get("type") == "intent"}
    place = {i: n for n, i in enumerate(order)}
    rows = [_intent_row(i, data.get(str(i["id"]), {})) for i in answer["items"] if i["type"] == "intent"]
    return sorted(rows, key=lambda r: (product_map.ended(r["status"]), place.get(r["id"], len(place)), ids.id_order(r["id"])))


def product_status(root: Path, cfg: config.Config | None) -> dict:
    """The product scope's map (schemas/product-status.schema.json, without its version field): its files, its items with
    the Intents that serve each, the Intents in order, and the forward check."""
    scope = product_scope.read(root, (cfg or config.EMPTY).product_dir)
    answer = current_work.open_work(root, cfg, include_done=True)
    found, _ = work_list.read_work(root, cfg)
    rows = _intents(answer, found, scope.order)
    serving: dict[str, list[str]] = {}
    for r in rows:
        if "serves" in r:
            serving.setdefault(r["serves"], []).append(r["id"])
    summary = answer.get("product_scope") or {"stalled": [], "in_flight_count": 0}
    return {
        "shape": [t for t in product_scope.HOLDING if t in scope.files],
        "files": [_file_row(root, cfg, f) for f in scope.files.values()],
        "items": [
            {"id": i.id, "type": i.type, "title": i.title, "status": i.status, **({"serves": i.serves} if i.serves else {}), "intents": serving.get(i.id, [])}
            for i in scope.items.values()
        ],
        "intents": rows,
        **summary,
        "uncovered": [{"id": i.id, "title": i.title} for i in product_map.uncovered(scope)],
        "findings": [findings.finding("status.unreadable_item", f.problems[0], path=f.path) for f in scope.files.values() if f.problems],
    }


def _line(text: str) -> str:
    return documents.one_line(text, 300)


def _file_lines(rows: list[dict]) -> list[str]:
    lines = []
    for f in rows:
        said = {
            APPROVED: f"approved by {f.get('approved_by')} on {f.get('approved_at')}",
            CHANGED: f"changed since approval ({f.get('changed')})",
            UNREADABLE: "unreadable: `aidd validate` says why",
        }.get(f["state"], f["state"].replace("_", " "))
        lines.append(f"  {f['path']}: {said}")
        if "next" in f:
            lines.append(f"    next ({f['next']['who']}): {f['next']['what']}")
    return lines


def _intent_line(row: dict) -> str:
    bits = [f"serves {row['serves']}" if "serves" in row else "serves nothing"]
    bits += [f"blocked by {', '.join(row['blocked_by'])}"] if row.get("blocked_by") else []
    bits += [f"owner {row['owner']}"] if row.get("owner") else []
    bits += [f"{row['progress']['finished']}/{row['progress']['total']}"] if row.get("progress") else []
    for c in row.get("criteria") or []:
        if result := c.get("result"):
            bits.append(f"{c['id']} {result['decision']} on {result['measured_on']}")
    return f"  {row['id']} {row['title']} ({row['status']}): {'; '.join(bits)}  {row.get('path', '')}"


def product_status_text(answer: dict) -> str:
    """`aidd status product` as a person reads it: the files and what each waits for, the items with their Intents, the
    stalled items, the Intents in flight, and the Intents in order."""
    if not answer["files"]:
        return NOTHING + "\n"
    lines = [f"The product scope is {SHAPES.get(tuple(answer['shape']), 'an intent order alone')}.", *_file_lines(answer["files"])]
    lines.append(f"In flight: {work_list.in_flight_words(answer['in_flight_count'], answer.get('max_in_flight'))}.")
    for s in answer["stalled"]:
        lines += [
            f"Stalled: {s['id']} {s['title']}: no Intent that is approved or active serves it",
            f"  next ({s['next']['who']}): {s['next']['what']}",
        ]
    lines += [f"No outcome serves {u['id']} {u['title']}: ask a person to add one to the PRD" for u in answer["uncovered"]]
    for i in answer["items"]:
        served = f" serves {i['serves']};" if "serves" in i else ""
        lines.append(f"{i['id']} {i['title']} ({i['type']}, {i['status']}):{served} {', '.join(i['intents']) or 'no Intent'}")
    lines += [_intent_line(r) for r in answer["intents"]]
    return "\n".join(_line(x) for x in lines) + "\n"
