"""The open work, as `aidd status` and the MCP `status` tool show it: each Spec, Epic, Initiative, and proposal in the
repository with its status, what blocks it, and the next step and who takes it. Read from the files alone."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from aidd import config
from aidd.kernel import documents
from aidd.workitems import backlog, due_dates, objects, status
from aidd.workitems.steps import STEP_CODES, STEP_MEANINGS

OPEN_GROUPS = ("backlog", "unstarted", "started")


def _step(code: str, what: str = "") -> dict:
    return {"code": code, "who": STEP_CODES[code], "what": what or STEP_MEANINGS[code]}


def spec_step(data: dict, state: str, blocked: list[str], cfg: config.Config | None) -> dict:
    """The next step of a Spec in `state`."""
    sid = data.get("id")
    if (data.get("suggested_by") or "").startswith("agent:") and not data.get("triage"):
        return _step("spec.triage")
    if data.get("route") == "emergency" and state not in status.TERMINAL:
        return _step("spec.emergency")
    if blocked:
        return _step("spec.blocked_by" if any(b.startswith("blocked by") for b in blocked) else "spec.blocked", "; ".join(blocked))
    if state == "draft":
        return _step("spec.draft")
    if state == "ready":
        who = ", ".join(data.get("approvers") or (cfg.approvers if cfg else [])) or "the person who directs the agents"
        return _step("spec.approval", f"the agent asked for Spec approval of {sid}: {who} answers yes, or says what to change")
    if state in ("approved", "in_progress"):
        todo = [t for t in status.task_states(data, state) if t["status"] == "todo"]
        names = ", ".join(str(t["id"]) for t in todo)
        code = "spec.approved" if state == "approved" else "spec.in_progress"
        return _step(code, STEP_MEANINGS[code] + (f": next {names}" if names else ""))
    if state == "in_review":
        return _step("spec.merge")
    if state == "rolled_back":
        return _step("spec.rolled_back")
    if state == "cancelled":
        return _step("spec.cancelled")
    return _step("spec.done")


def open_work(root: Path, cfg: config.Config | None, *, today: dt.date | None = None, include_done: bool = False) -> dict:
    """Every work item and its next step (schemas/status.schema.json, without its version field)."""
    today = today or dt.date.today()
    specs_dir = cfg.specs_dir if cfg else "specs"
    found: list[tuple[str, dict]] = []
    unreadable: list[dict] = []
    for p in objects.object_files(root, specs_dir) + sorted((root / (cfg.proposals_dir if cfg else "proposals")).glob("*/proposal.md")):
        try:
            data, _ = documents.split_front_matter(p.read_text(encoding="utf-8", errors="replace"), p.as_posix())
        except (documents.DocumentError, OSError) as exc:
            # Never dropped without a word: a Spec that does not parse is still open work, and someone must fix it.
            unreadable.append({"path": p.relative_to(root).as_posix(), "error": documents.one_line(str(exc), 200)})
            continue
        if isinstance(data, dict) and data.get("type") in (*backlog.WORK_TYPES, "proposal"):
            found.append((p.relative_to(root).as_posix(), data))
    idx = {str(d.get("id")): d for _, d in found if d.get("id")}
    work = [d for _, d in found if d.get("type") in backlog.WORK_TYPES]
    specs = {str(d.get("id")): status.spec_status(d) for d in work if d.get("type") == "spec"}
    states, progress, children = status.container_statuses(work, specs)
    items = []
    for path, d in found:
        oid, kind = str(d.get("id")), str(d.get("type"))
        if kind == "proposal":
            state = str(d.get("status") or "qualifying")
            code = {
                "qualifying": "proposal.qualifying",
                "drafting": "proposal.drafting",
                "signed_off": "proposal.signed_off",
                "submitted": "proposal.submitted",
                "accepted": "proposal.accepted",
            }.get(state)
            step = _step(code) if code else None
            group = "completed" if state in ("accepted", "declined", "withdrawn") else "started"
        else:
            state = states.get(oid, status.spec_status(d))
            waits = backlog.waiting_on(d, idx, lambda o: status.status_unblocks(states.get(o, "draft")))
            blocked = status.blocked_reasons(d, state, waits)
            if kind == "spec":
                step = spec_step(d, state, blocked, cfg)
                due_on = status.outcome_due(d, state, today)
                if due_on is not None:
                    step = _step("spec.outcome_due", f"the hypothesis was due {due_on}: measure it and record `outcome.result`")
            else:
                kids = children.get(oid, [])
                done = kids and all(status.finished(states.get(c, "draft")) for c in kids) and state not in ("done", "cancelled")
                step = _step(f"{kind}.close") if done else None
            group = backlog.group(d, state) or "backlog"
        if not include_done and group not in OPEN_GROUPS and not (step and step["code"] == "spec.outcome_due"):
            continue
        item: dict[str, object] = {"id": oid, "type": kind, "title": str(d.get("title") or ""), "path": path, "status": state, "group": group}
        if d.get("route"):
            item["route"] = d["route"]
        if kind in ("epic", "initiative") and oid in progress:
            item["progress"] = {"finished": progress[oid][0], "of": progress[oid][1]}
        if step:
            item["next"] = step
        items.append(item)
    due = [
        {"path": p, "what": f"flag {f.get('name')} was due for removal on {f.get('cleanup_due')}", "next": _step("flag.overdue")}
        for p, _, f in due_dates.overdue_flags(found, today, specs)
    ] + [
        {"path": p, "what": f"deprecation {x.get('what')} passed its sunset on {x.get('sunset')}", "next": _step("deprecation.overdue")}
        for p, _, x in due_dates.overdue_deprecations(found, today, specs)
    ]
    order = {"started": 0, "unstarted": 1, "backlog": 2, "completed": 3, "cancelled": 4}
    items.sort(key=lambda i: (order.get(str(i["group"]), 5), status.item_priority(idx.get(str(i["id"]), {}), idx) != "urgent", str(i["id"])))
    out: dict = {"items": items, "due": due}
    if unreadable:
        out["unreadable"] = unreadable
    if not items and not due and not unreadable:
        out["next"] = _step("nothing_open")
    return out


def status_text(answer: dict, *, mine: str | None = None) -> str:
    """`aidd status` as a person reads it: one block per item, then what is past due."""
    lines: list[str] = []
    for i in answer["items"]:
        step = i.get("next")
        if mine and (not step or step["who"] != mine):
            continue
        extra = f" {i['progress']['finished']}/{i['progress']['of']}" if "progress" in i else ""
        route = f", {i['route']}" if i.get("route") else ""
        lines.append(f"{i['id']} {i['title']} ({i['type']}{route}): {i['status']}{extra}  {i['path']}")
        if step:
            lines.append(f"  next ({step['who']}): {step['what']}")
    for d in answer["due"]:
        lines.append(f"due: {d['what']} ({d['path']}); next: {d['next']['what']}")
    for u in answer.get("unreadable", []):
        lines.append(f"unreadable: {u['path']}: {u['error']}; fix its front matter, then `aidd validate {u['path']}`")
    if "next" in answer:
        lines.append(answer["next"]["what"])
    if not lines:
        lines.append("nothing waits on you" if mine == "person" else "nothing open matches")
    return "\n".join(lines) + "\n"
