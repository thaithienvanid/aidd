"""The open work, as `aidd status` and the MCP `status` tool show it: each Spec, Intent, and proposal in the repository
with its status, the stage a Spec stands in, an Intent's phases, what blocks it, and the next step and who takes it. Read
from the files alone."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from aidd import config
from aidd.kernel import documents, json_schema
from aidd.workitems import backlog, due_dates, ids, intents, interfaces, objects, spec_file, status, step_reasons
from aidd.workitems.steps import STEP_CODES, STEP_MEANINGS, step_words

OPEN_GROUPS = ("backlog", "unstarted", "started")


def _step(code: str, what: str = "") -> dict:
    return {"code": code, "who": STEP_CODES[code], "what": what or STEP_MEANINGS[code]}


def step_of_code(code: str) -> dict:
    """The step `code` names, with who takes it and what it means, before its words."""
    return _step(code)


def spoken(step: dict, ident: object, *, person: str = "", waits: tuple[str, ...] | list[str] = (), route: object = None) -> dict:
    """`step` with who answers (for a step a person takes), the words to say or run, and why it comes next, read from the
    data that owns the reason (`step_reasons`), as `schemas/status.schema.json` has them. `route` picks the item's lane."""
    words = step_words(step["code"], ident, waits=waits)
    why = step_reasons.step_reason(step["code"], route)
    return {
        **step,
        **({"person": person} if person and step["who"] == "person" else {}),
        **({"words": words} if words else {}),
        **({"why": why} if why else {}),
    }


def _person(data: dict, code: str, cfg: config.Config | None) -> str:
    """Who answers a person's step: the first approver for an approval (the Spec's, else the config's), else the owner."""
    if code in ("spec.approval", "spec.merge"):
        for name in [*(data.get("approvers") or []), *(cfg.approvers if cfg else [])]:
            return str(name)
    return str(data["owner"]) if isinstance(data.get("owner"), str) else ""


def _whole_emergency(found: object) -> bool:
    """Whether an `emergency` is valid under the common schema (severity, type, commander, and a review date that is a date),
    so the answer never carries half of one, and a timestamp in `review_due` is no date."""
    return isinstance(found, dict) and not json_schema.validate(found, "common.schema.json#/$defs/emergency")


def _facts(data: dict, item_type: str, state: str) -> dict:
    """The facts a page shows, each copied from the one place that owns it: the owner and the blockers from the item's front
    matter, each Task's state from `status.task_states`, and the emergency."""
    out: dict = {}
    if isinstance(data.get("owner"), str) and data["owner"]:
        out["owner"] = data["owner"]
    if item_type == "spec":
        if str(data.get("blockers") or "").strip():
            out["blockers"] = str(data["blockers"])
        tried = {str(t.get("id")): int(t.get("retry_count") or 0) for t in data.get("tasks") or [] if isinstance(t, dict)}
        tasks = [
            {
                "id": str(t["id"]),
                "title": str(t.get("title") or ""),
                "status": t["status"],
                "retry_count": tried.get(str(t["id"]), 0),
                **({"why": t["why"]} if t.get("why") else {}),
            }
            for t in status.task_states(data, state)
        ]
        if tasks:
            out["tasks"] = tasks
        if _whole_emergency(data.get("emergency")):
            out["emergency"] = data["emergency"]
    return out


def _noted(step: dict, note: str) -> dict:
    """`step` with `note` after its words."""
    return {**step, "what": f"{step['what']} ({note})"} if note else step


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
        if consumers:
            return _step("spec.consumers", f"{STEP_MEANINGS['spec.consumers']} ({consumers})")
        return _step("spec.planned" if status.is_planned(data, state) else "spec.draft")
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


def intent_step(data: dict, state: str, kids: list[str], ready: list[str], agreed: dict | None) -> dict | None:
    """The next step of an Intent in `state`, whose children are in `kids` and whose `ready` slices may start: a person
    closes it once every child is finished; a person agrees to it before Specify starts on a slice, until `agreed`, the
    Intent as the person agreed to it, says an agreement stands; then the agent starts its ready slices. A slice or
    the goal changed since `agreed` asks the person to agree again, and only the slices they agreed to may start
    meanwhile. None when it is closed, or nothing is ready."""
    if state in ("done", "cancelled"):
        return None
    if kids and all(status.finished(k) for k in kids):
        return _step("intent.close")
    if agreed is None:
        return _step("intent.agree") if intents.slice_ids(data) else None
    if changes := intents.changes_since(agreed, data):
        ready = [s for s in ready if s in intents.slice_ids(agreed)]
        meanwhile = f"; {', '.join(ready[: intents.READY_SHOWN])} may start meanwhile" if ready else ""
        return _noted(_step("intent.agree"), f"{'; '.join(changes)} since the agreement, and a new slice waits for it{meanwhile}")
    if ready:
        return _step("intent.slice", f"{STEP_MEANINGS['intent.slice']}: next {', '.join(ready[: intents.READY_SHOWN])}")
    return None


def person_agreed(data: dict) -> bool:
    """Whether an Intent's file says a person agreed: `agreed_at`, and an `agreed_by` in a person's form."""
    who = str(data.get("agreed_by") or "")
    return bool(data.get("agreed_at")) and bool(who) and config.approved_by_kind(who) is None


def read_work(root: Path, cfg: config.Config | None) -> tuple[list[tuple[str, dict]], list[dict]]:
    """Every Spec, Intent, and proposal file as (repo-relative path, front matter), and the files that do not parse."""
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
        elif isinstance(data, dict) and data.get("type") in objects.FOLDED_TYPES:
            unreadable.append({"path": rel, "error": f"type {data['type']} {spec_file.FOLDED_FIX}"})
    return found, unreadable


Keep = Callable[[dict], bool]


def in_delivery_team(data: dict, team: dict, scope_areas: Callable[[list[str]], Iterable[str]], *, name: str = "") -> bool:
    """Whether work item `data` is the work of delivery team `team` (config `delivery_teams`), called `name`: one of its
    Intents, a Spec under one, a Spec whose `owner_team` names it, or a Spec whose Task scope touches one of its areas.
    `scope_areas` gives the areas a scope touches, as `aidd risk --paths` reads them."""
    owned = {str(e) for e in team.get("intents") or []}
    if data.get("type") == "intent":
        return str(data.get("id")) in owned
    if data.get("type") != "spec":
        return False
    if str(data.get("parent") or "") in owned or (name and str(data.get("owner_team") or "").lower() == name.lower()):
        return True
    tasks = data.get("tasks")
    tasks = tasks if isinstance(tasks, list) else []
    scope = [str(p) for t in tasks if isinstance(t, dict) and isinstance(t.get("scope"), list) for p in t["scope"]]
    areas = set(team.get("areas") or [])
    return bool(areas and scope) and not areas.isdisjoint(scope_areas(scope))


Teams = Callable[[dict], list[str]]


@dataclass(frozen=True)
class Shown:
    """What an answer shows: `keep` picks the items, such as one delivery team's, and `teams` is the rule that names the
    delivery teams whose work an item is, so each item says which and the answer lists the config's teams."""

    keep: Keep | None = None
    teams: Teams | None = None


EVERYTHING = Shown()


def raw_emergencies(root: Path, cfg: config.Config | None) -> dict[str, dict]:
    """Each Spec's `emergency` object as its front matter holds it, by the Spec's path, whole or not. `--json` leaves a broken
    object out, so its schema holds; the page keeps each field that is good, and says which are missing or unreadable."""
    found, _ = read_work(root, cfg)
    return {path: d["emergency"] for path, d in found if d.get("type") == "spec" and isinstance(d.get("emergency"), dict)}


def team_names(cfg: config.Config | None) -> list[str]:
    """The config's delivery teams, in its order."""
    return [str(n) for n in (cfg.get("delivery_teams", default={}) or {})] if cfg else []


ROUTES = ("minor", "normal", "major", "emergency")


def _probe(path: str, d: dict, cfg: config.Config | None, today: dt.date) -> None:
    """Read each field the answer uses from one item alone, in every state a Spec can be in, so a field of the wrong type
    raises here, where the item can be set aside, and never in the middle of the answer for every item."""
    oid, item_type = str(d.get("id")), str(d.get("type"))
    states, _, _ = intents.intent_statuses([d] if item_type in backlog.WORK_TYPES else [], {oid: status.spec_status(d)} if item_type == "spec" else {})
    waits = backlog.waiting_on(d, {oid: d}, lambda o: True)
    for state in ("draft", "ready", "approved", "in_progress", "in_review", states.get(oid, "draft")):
        blocked = status.blocked_reasons(d, state, waits)
        if item_type == "spec":
            step = spec_step(d, state, blocked, cfg, interfaces.consumer_note(d, {oid: d}, {oid: state}))
            _person(d, step["code"], cfg)
            status.outcome_due(d, state, today)
            intents.spec_stage(d, state, today)
        _facts(d, item_type, state)
    if item_type == "intent":
        intents.phase_view(d, {}, {}, today)
        intent_step(d, states.get(oid, "draft"), [], intents.ready_slices(d, states, {}), d if person_agreed(d) else None)
    status.item_priority(d, {oid: d})
    due_dates.overdue_flags([(path, d)], today)
    due_dates.overdue_deprecations([(path, d)], today)


def open_items(
    found: list[tuple[str, dict]],
    unreadable: list[dict],
    cfg: config.Config | None,
    *,
    today: dt.date | None = None,
    include_done: bool = False,
    shown: Shown = EVERYTHING,
    validates: Callable[[str], bool] | None = None,
    agreed: Callable[[str, dict], dict | None] | None = None,
) -> dict:
    """`current_work.open_work` of the work items already read: (path, front matter) pairs, and the files that did not parse. Every
    item still counts toward a block and an Intent's progress; `shown.keep` only picks the items shown. `validates(path)` says a
    draft Spec's file is finished (`validates_clean`); without it, a draft reads as unfinished, as in a branch's tip.
    `agreed(path, front matter)` gives the Intent as the person agreed to it, as a commit records it, or None when no agreement
    stands; without it, as in a branch's tip, the file must name a person, and it is the version agreed."""
    today = today or dt.date.today()
    teams = shown.teams
    readable = []
    for path, d in found:  # an item with a field of the wrong type is set aside as unreadable, whole, so `aidd validate` names it
        try:
            _probe(path, d, cfg, today)
        except (TypeError, ValueError, AttributeError, KeyError) as exc:
            unreadable = [*unreadable, {"path": path, "error": documents.one_line(f"a field has the wrong type ({type(exc).__name__}: {exc})", 200)}]
        else:
            readable.append((path, d))
    found = readable
    shown_paths = {path for path, d in found if shown.keep is None or shown.keep(d)}
    idx = {str(d.get("id")): d for _, d in found if d.get("id")}
    work = [d for _, d in found if d.get("type") in backlog.WORK_TYPES]
    specs = {str(d.get("id")): status.spec_status(d) for d in work if d.get("type") == "spec"}
    spec_data = {oid: idx[oid] for oid in specs if oid in idx}
    states, progress, children = intents.intent_statuses(work, specs)
    items = []
    waiting: dict[str, list[str]] = {}
    for path, d in found:
        if path not in shown_paths:
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
                consumers = interfaces.consumer_note(d, spec_data, specs)
                step = spec_step(d, state, blocked, cfg, consumers)
                if step["code"] in ("spec.draft", "spec.consumers") and validates is not None and validates(path):
                    heard = (
                        f"; it provides an interface that open Specs consume, so name them and their owners in the question ({consumers})" if consumers else ""
                    )
                    step = _step("spec.ask_approval", STEP_MEANINGS["spec.ask_approval"] + heard)
                if waits and step["code"] in ("spec.planned", "spec.draft", "spec.consumers", "spec.ask_approval", "spec.approval"):
                    step = _noted(step, f"Implement waits for {', '.join(waits)}")
                due_on = status.outcome_due(d, state, today)
                if due_on is not None:
                    step = _step("spec.outcome_due", f"the hypothesis was due {due_on}: measure it and record `outcome.result`")
            else:
                kids, ready = [states.get(c, "draft") for c in children.get(oid, [])], intents.ready_slices(d, states, specs)
                then = (d if agreed is None else agreed(path, d)) if person_agreed(d) else None
                step = intent_step(d, state, kids, ready, then)
            group = backlog.group(d, state) or "backlog"
        if not include_done and group not in OPEN_GROUPS and not (step and step["code"] == "spec.outcome_due"):
            continue
        item: dict[str, object] = {"id": oid, "type": item_type, "title": str(d.get("title") or ""), "path": path, "status": state, "group": group}
        if d.get("route") in ROUTES:  # a route outside the schema's list is left out, so the answer stays valid
            item["route"] = d["route"]
        if d.get("parent"):
            item["parent"] = str(d["parent"])
        if isinstance(d.get("owner_team"), str) and d["owner_team"]:
            item["owner_team"] = d["owner_team"]
        if teams is not None and (names := teams(d)):
            item["delivery_teams"] = names
        if waiting.get(oid):
            item["waiting_on"] = waiting[oid]
        if item_type == "spec" and (stage := intents.spec_stage(d, state, today)):
            item["stage"] = stage
        if item_type == "intent" and oid in progress:
            item["progress"] = {"finished": progress[oid][0], "of": progress[oid][1]}
        if item_type == "intent" and (phases := intents.phase_view(d, specs, spec_data, today)):
            item["phases"] = phases
        item.update(_facts(d, item_type, state))
        if step:
            item["next"] = spoken(step, d.get("id"), person=_person(d, step["code"], cfg), waits=waiting.get(oid, ()), route=d.get("route"))
        items.append(item)
    due = [
        {
            "path": p,
            "what": f"flag {f.get('name')} was due for removal on {f.get('cleanup_due')}",
            "next": spoken(_step("flag.overdue"), spec.get("id")),
        }
        for p, spec, f in due_dates.overdue_flags(found, today, specs)
        if p in shown_paths
    ] + [
        {
            "path": p,
            "what": f"deprecation {x.get('what')} passed its sunset on {x.get('sunset')}",
            "next": spoken(_step("deprecation.overdue"), spec.get("id")),
        }
        for p, spec, x in due_dates.overdue_deprecations(found, today, specs)
        if p in shown_paths
    ]
    order = {"started": 0, "unstarted": 1, "backlog": 2, "completed": 3, "cancelled": 4}
    items.sort(key=lambda i: (order.get(str(i["group"]), 5), status.item_priority(idx.get(str(i["id"]), {}), idx) != "urgent", ids.id_order(str(i["id"]))))
    out: dict = {"items": items, "due": due}
    if note := stall_note(out):
        out["root_blocker"] = note
    if unreadable:
        out["unreadable"] = unreadable
    if teams is not None and (names := team_names(cfg)):
        out["delivery_teams"] = names
    if not items and not due and not unreadable:
        out["next"] = spoken(_step("nothing_open"), "")
    return out


# What the agent does to move a root blocker on, by its step.
_MOVE_ON = {
    "spec.planned": "specify it",
    "spec.draft": "finish it",
    "spec.consumers": "finish it",
    "spec.ask_approval": "set it ready and ask for its approval",
    "spec.approved": "build it",
    "spec.in_progress": "build and merge it",
}


def _wait_cycle(waits: dict[str, list[str]]) -> list[str]:
    """One ring of items that wait on each other, as ids, or [] when there is none."""

    def walk(node: str, path: list[str]) -> list[str]:
        if node in path:
            return path[path.index(node) :]
        for nxt in waits.get(node, []):
            if ring := walk(nxt, [*path, node]):
                return ring
        return []

    for start in sorted(waits, key=ids.id_order):
        if ring := walk(start, []):
            return ring
    return []


def stall_note(answer: dict) -> str | None:
    """When the open work has steps and none is a person's: each item that Specs wait behind, with how many, and the
    pick; or the ring of items that wait on each other. None when a person has a step, or nothing is open."""
    items = [i for i in answer["items"] if i.get("group") in OPEN_GROUPS]
    owed = [*items, *answer["due"], *answer.get("explorations", [])]
    if not items or any((i.get("next") or {}).get("who") == "person" for i in owed):
        return None
    waits = {str(i["id"]): [str(w) for w in i.get("waiting_on", [])] for i in items}
    behind: dict[str, set[str]] = {}
    for sid, ws in waits.items():
        for w in ws:
            behind.setdefault(w, set()).add(sid)
    for held in list(behind):  # whoever waits on a waiting item waits behind this one too
        todo = list(behind[held])
        while todo:
            for more in behind.get(todo.pop(), ()):
                if more not in behind[held]:
                    behind[held].add(more)
                    todo.append(more)
    kinds = {str(i["id"]): i["type"] for i in items}
    counts = {r: len({s for s in dep if kinds.get(s) == "spec" and s != r}) for r, dep in behind.items() if not waits.get(r)}
    roots = sorted((r for r, n in counts.items() if n), key=lambda r: (-counts[r], ids.id_order(r)))
    if not roots:
        if ring := _wait_cycle(waits):
            return f"{', '.join(ring)} wait on each other, so none can go first: remove one `blocked_by` from them, then run `aidd validate`."
        return "Your agent holds every open step: choose a Spec to specify or build next, and tell it which."
    parts = []
    for root in roots:
        step = next((i.get("next") or {} for i in items if str(i["id"]) == root), {})
        parts.append(f"{root} blocks {counts[root]} Spec{'' if counts[root] == 1 else 's'}: {_MOVE_ON.get(step.get('code', ''), 'move it on')}")
    return (parts[0] + "," if len(parts) == 1 else "; ".join(parts) + ";") + " or choose a Spec to specify."


def _first_lines(answer: dict, mine: str | None) -> list[str]:
    """What `aidd status` says before the items: where the work on this branch stopped, by its last commit's note, and
    each open exploration, whose pick a person owes."""
    lines = []
    if (h := answer.get("handoff")) and mine is None:
        said = "; ".join(f"{k.replace('_', ' ')}: {h[k]}" for k in ("done", "next", "needs", "stopped_at") if h.get(k))
        lines.append(f"where the work stopped, by the note in {h['branch']}'s last commit ({h['commit']}), the agent's account: {said}")
    for e in answer.get("explorations", []) if mine in (None, "person") else []:
        lines.append(f"{e.get('item') or 'no work item'}: an open question: {e['question']}  {e['path']}")
        lines.append(f"  next (person): {e['next']['what']}")
        lines += [f"  why: {e['next']['why']}"] if e["next"].get("why") else []
    return lines


def status_text(answer: dict, *, mine: str | None = None, pick: bool = True) -> str:
    """`aidd status` as a person reads it: one block per item, then what is past due. With `pick`, and no step a person's,
    it ends with the root blocker and the choice."""
    lines = _first_lines(answer, mine)
    planned = 0
    for i in answer["items"]:
        step = i.get("next")
        if mine and (not step or step["who"] != mine):
            continue
        extra = f" {i['progress']['finished']}/{i['progress']['of']}" if "progress" in i else ""
        route = f", {i['route']}" if i.get("route") else ""
        # A planned Spec shows as planned, and its one shared step is said once, after the list.
        is_planned = bool(step) and step["code"] == "spec.planned"
        planned += is_planned
        stage = f" · {i['stage']} stage" if i.get("stage") and not is_planned else ""
        lines.append(f"{i['id']} {i['title']} ({i['type']}{route}): {'planned' if is_planned else i['status']}{extra}{stage}  {i['path']}")
        if i.get("phases") and (progress := intents.phase_line(i)):
            lines.append(f"  {progress}")
        if i.get("places"):
            lines.append(f"  in: {', '.join(i['places'])}")
        if step and not is_planned:
            lines.append(f"  next ({step['who']}): {step['what']}")
            lines += [f"  why: {step['why']}"] if step.get("why") else []
        if u := i.get("unsaved"):
            shown = ", ".join(u["paths"][:3]) + (", ..." if u["count"] > 3 else "")
            lines.append(
                f"  unsaved: {u['count']} path{'' if u['count'] == 1 else 's'} on {u['branch']} not committed ({shown}): commit them there, so a stop loses nothing"
            )
    if planned:
        lines.append(f"next ({STEP_CODES['spec.planned']}), for the {planned} planned Spec{'' if planned == 1 else 's'}: {STEP_MEANINGS['spec.planned']}")
        lines.append(f"  why: {step_reasons.step_reason('spec.planned')}")
    for d in answer["due"]:
        lines.append(f"due: {d['what']} ({d['path']}); next: {d['next']['what']}")
    for u in answer.get("unreadable", []):
        where = f"{u['place']}: " if u.get("place") else ""
        lines.append(f"unreadable: {where}{u['path']}: {u['error']}; fix its front matter, then `aidd validate {u['path']}`")
    if "next" in answer:
        lines.append(answer["next"]["what"])
    note = stall_note(answer) if pick and mine in (None, "person") else None
    if note and mine and not lines:
        lines.append("nothing waits on you")
    if note:
        lines.append(note)
    if not lines:
        lines.append("nothing waits on you" if mine == "person" else "nothing open matches")
    # Every field comes from a file, and a fetched branch's file is another's text: each line prints as one safe line.
    return "\n".join(documents.one_line(line, 4000) for line in lines) + "\n"
