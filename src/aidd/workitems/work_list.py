"""The open work, as `aidd status` and the MCP `status` tool show it: each Spec, Epic, Initiative, and proposal in the
repository with its status, what blocks it, and the next step and who takes it. Read from the files alone."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable
from pathlib import Path

from aidd import config
from aidd.kernel import documents
from aidd.workitems import backlog, due_dates, interfaces, objects, status
from aidd.workitems.steps import STEP_CODES, STEP_MEANINGS

OPEN_GROUPS = ("backlog", "unstarted", "started")


def _step(code: str, what: str = "") -> dict:
    return {"code": code, "who": STEP_CODES[code], "what": what or STEP_MEANINGS[code]}


def spec_step(data: dict, state: str, blocked: list[str], cfg: config.Config | None, consumers: str = "") -> dict:
    """The next step of a Spec in `state`. `consumers` names the open Specs that consume an interface it provides, once revised."""
    sid = data.get("id")
    if (data.get("suggested_by") or "").startswith("agent:") and not data.get("triage"):
        return _step("spec.triage")
    if data.get("route") == "emergency" and state not in status.TERMINAL:
        return _step("spec.emergency")
    if blocked:
        # A blocker a person must clear keeps the step theirs, even when the Spec also waits for other work.
        return _step("spec.blocked" if any(not b.startswith("blocked by") for b in blocked) else "spec.blocked_by", "; ".join(blocked))
    if state == "draft":
        return _step("spec.consumers", f"{STEP_MEANINGS['spec.consumers']} ({consumers})") if consumers else _step("spec.draft")
    if state == "ready":
        who = ", ".join(data.get("approvers") or (cfg.approvers if cfg else [])) or "the person who directs the agents"
        heard = f"; it provides an interface that open Specs consume, so their owners hear first ({consumers})" if consumers else ""
        return _step("spec.approval", f"the agent asked for Spec approval of {sid}: {who} answers yes, or says what to change{heard}")
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


def read_work(root: Path, cfg: config.Config | None) -> tuple[list[tuple[str, dict]], list[dict]]:
    """Every Spec, Epic, Initiative, and proposal file as (repo-relative path, front matter), and the files that do not parse."""
    specs_dir = cfg.specs_dir if cfg else "specs"
    texts: list[tuple[str, str]] = []
    unreadable: list[dict] = []
    for p in objects.object_files(root, specs_dir) + sorted((root / (cfg.proposals_dir if cfg else "proposals")).glob("*/proposal.md")):
        rel = p.relative_to(root).as_posix()
        try:
            texts.append((rel, p.read_text(encoding="utf-8", errors="replace")))
        except OSError as exc:
            unreadable.append({"path": rel, "error": documents.one_line(str(exc), 200)})
    found, bad = parse_work(texts)
    return found, unreadable + bad


def parse_work(texts: list[tuple[str, str]]) -> tuple[list[tuple[str, dict]], list[dict]]:
    """The work items among (repo-relative path, text) pairs, as (path, front matter), and the files that do not parse."""
    found: list[tuple[str, dict]] = []
    unreadable: list[dict] = []
    for rel, text in texts:
        try:
            data, _ = documents.split_front_matter(text, rel)
        except documents.DocumentError as exc:
            # Never dropped without a word: a Spec that does not parse is still open work, and someone must fix it.
            unreadable.append({"path": rel, "error": documents.one_line(str(exc), 200)})
            continue
        if isinstance(data, dict) and data.get("type") in (*backlog.WORK_TYPES, "proposal"):
            found.append((rel, data))
    return found, unreadable


Keep = Callable[[dict], bool]


def in_delivery_team(data: dict, team: dict, scope_areas: Callable[[list[str]], Iterable[str]]) -> bool:
    """Whether work item `data` is the work of delivery team `team` (config `delivery_teams`): one of its Epics, a Spec
    under one, or a Spec whose Task scope touches one of its areas. `scope_areas` gives the areas a scope touches, as
    `aidd risk --paths` reads them."""
    epics = {str(e) for e in team.get("epics") or []}
    if data.get("type") == "epic":
        return str(data.get("id")) in epics
    if data.get("type") != "spec":
        return False
    if str(data.get("parent") or "") in epics:
        return True
    tasks = data.get("tasks")
    tasks = tasks if isinstance(tasks, list) else []
    scope = [str(p) for t in tasks if isinstance(t, dict) and isinstance(t.get("scope"), list) for p in t["scope"]]
    areas = set(team.get("areas") or [])
    return bool(areas and scope) and not areas.isdisjoint(scope_areas(scope))


def open_work(root: Path, cfg: config.Config | None, *, today: dt.date | None = None, include_done: bool = False, keep: Keep | None = None) -> dict:
    """Every work item and its next step (schemas/status.schema.json, without its version field); with `keep`, only the
    items it keeps, such as one delivery team's."""
    found, unreadable = read_work(root, cfg)
    return open_items(found, unreadable, cfg, today=today, include_done=include_done, keep=keep)


def open_items(
    found: list[tuple[str, dict]],
    unreadable: list[dict],
    cfg: config.Config | None,
    *,
    today: dt.date | None = None,
    include_done: bool = False,
    keep: Keep | None = None,
) -> dict:
    """`open_work` of the work items already read: (path, front matter) pairs, and the files that did not parse. Every
    item still counts toward a block and an Epic's progress; `keep` only picks the items shown."""
    today = today or dt.date.today()
    shown = {path for path, d in found if keep is None or keep(d)}
    idx = {str(d.get("id")): d for _, d in found if d.get("id")}
    work = [d for _, d in found if d.get("type") in backlog.WORK_TYPES]
    specs = {str(d.get("id")): status.spec_status(d) for d in work if d.get("type") == "spec"}
    spec_data = {oid: idx[oid] for oid in specs if oid in idx}
    states, progress, children = status.container_statuses(work, specs)
    items = []
    waiting: dict[str, list[str]] = {}
    for path, d in found:
        if path not in shown:
            continue
        oid, item_type = str(d.get("id")), str(d.get("type"))
        if item_type == "proposal":
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
            waiting[oid] = waits
            blocked = status.blocked_reasons(d, state, waits)
            if item_type == "spec":
                step = spec_step(d, state, blocked, cfg, interfaces.consumer_note(d, spec_data, specs))
                due_on = status.outcome_due(d, state, today)
                if due_on is not None:
                    step = _step("spec.outcome_due", f"the hypothesis was due {due_on}: measure it and record `outcome.result`")
            else:
                kids = children.get(oid, [])
                done = kids and all(status.finished(states.get(c, "draft")) for c in kids) and state not in ("done", "cancelled")
                step = _step(f"{item_type}.close") if done else None
            group = backlog.group(d, state) or "backlog"
        if not include_done and group not in OPEN_GROUPS and not (step and step["code"] == "spec.outcome_due"):
            continue
        item: dict[str, object] = {"id": oid, "type": item_type, "title": str(d.get("title") or ""), "path": path, "status": state, "group": group}
        if d.get("route"):
            item["route"] = d["route"]
        if d.get("parent"):
            item["parent"] = str(d["parent"])
        if waiting.get(oid):
            item["waiting_on"] = waiting[oid]
        if item_type in ("epic", "initiative") and oid in progress:
            item["progress"] = {"finished": progress[oid][0], "of": progress[oid][1]}
        if step:
            item["next"] = step
        items.append(item)
    due = [
        {"path": p, "what": f"flag {f.get('name')} was due for removal on {f.get('cleanup_due')}", "next": _step("flag.overdue")}
        for p, _, f in due_dates.overdue_flags(found, today, specs)
        if p in shown
    ] + [
        {"path": p, "what": f"deprecation {x.get('what')} passed its sunset on {x.get('sunset')}", "next": _step("deprecation.overdue")}
        for p, _, x in due_dates.overdue_deprecations(found, today, specs)
        if p in shown
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
        if i.get("places"):
            lines.append(f"  in: {', '.join(i['places'])}")
        if step:
            lines.append(f"  next ({step['who']}): {step['what']}")
    for d in answer["due"]:
        lines.append(f"due: {d['what']} ({d['path']}); next: {d['next']['what']}")
    for u in answer.get("unreadable", []):
        where = f"{u['place']}: " if u.get("place") else ""
        lines.append(f"unreadable: {where}{u['path']}: {u['error']}; fix its front matter, then `aidd validate {u['path']}`")
    if "next" in answer:
        lines.append(answer["next"]["what"])
    if not lines:
        lines.append("nothing waits on you" if mine == "person" else "nothing open matches")
    # Every field comes from a file, and a fetched branch's file is another's text: each line prints as one safe line.
    return "\n".join(documents.one_line(line, 4000) for line in lines) + "\n"
