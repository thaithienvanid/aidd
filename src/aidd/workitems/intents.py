"""Intents: work bigger than one Spec, with its slices grouped into phases, and the stage each change stands in.

An Intent lists its slices, one line each, in `phases`; one with one phase lists that one. A slice is a planned Spec: it
becomes a Spec file when its work starts (`aidd new spec <id>`), and until then it is a line. A slice with no Spec file
is finished once its line records `merged_in`.

A stage groups loop steps for people, in the order `graph.stages` in `schemas/roles.json` gives. A Spec stands in the
stage of the step its stored status and its Tasks put it at, read from its file alone, never from a report.
"""

from __future__ import annotations

import datetime as dt
import functools
import re

from aidd import knowledge
from aidd.kernel import json_schema, retired_names, timestamps
from aidd.workitems import criteria, old_shape, status

# A slice's status when it has no Spec file: `planned` until its line records `merged_in`, then `done`.
PLANNED = "planned"
# How many ready slices `aidd status` names as the next to start: the lead starts two or three at a time.
READY_SHOWN = 3
# A day as a progress line says it, in English whatever the locale: "14 Nov".
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_WINDOW = re.compile(r"^([0-9]+)([mhd])$")


def phases_of(data: dict) -> list[dict]:
    """The Intent's phases, in order, each `{id, name, specs}` with what else it holds. A field of the wrong shape counts as empty."""
    if isinstance(data.get("phases"), list):
        return [p for p in data["phases"] if isinstance(p, dict)]
    return []


def planned_specs_of(phase: dict) -> list[dict]:
    """A phase's planned Specs that carry an id, in order."""
    found = phase.get("specs")
    return [s for s in found if isinstance(s, dict) and s.get("id")] if isinstance(found, list) else []


def planned_spec_ids(data: dict) -> list[str]:
    """Every slice id the Intent lists, in phase order, once each."""
    return list(dict.fromkeys(str(s["id"]) for p in phases_of(data) for s in planned_specs_of(p)))


def planned_spec_lines(items: list[dict]) -> dict[str, tuple[dict, dict, dict]]:
    """Each slice by its id: (the Intent, its phase, the slice line), the first Intent that lists it."""
    out: dict[str, tuple[dict, dict, dict]] = {}
    for d in items:
        if d.get("type") != "intent":
            continue
        for p in phases_of(d):
            for s in planned_specs_of(p):
                out.setdefault(str(s["id"]), (d, p, s))
    return out


def planned_spec_blocked_by(line: dict) -> list[str]:
    """The ids a slice line waits for."""
    found = line.get("blocked_by")
    return [str(i) for i in found if i] if isinstance(found, list) else []


# What an agent keeps writing in an approved Intent, so a change to it is no change of what the person approved. Everything else in the
# front matter, and the whole body, is covered, so a field added to the schema later is covered until a person lists it here. Each entry
# says what it lets through and what `_kept_changes` takes back of it. A criterion's drafted `result` is kept too (`_without_draft`), and
# `_kept_changes` takes back a change or a removal of one the agreed version holds. A result that carries an `approval` is a person's yes
# and is never kept, so a change to it is a change of what the person agreed to.
AGENT_KEPT = (
    "waiting_on",  # a pause flag that a person answers and clears; setting it leaves the agreed plan as it stood
    "blocked_by",  # the plan's links, which a merge keeps current. Lets through an added blocker. Takes back a removed one, which would free its Specs early.
    "owner",  # who holds the work day to day: it approves nothing, and a yes stays the person's own words
    "development_team",  # routing to a team's roles: no aidd check reads a team field. Take it out if one ever reads `approvers` from it
    "trace_id",  # joins the Specs of other repositories: aidd reads no other repository, and no approval crosses one
    "tracker",  # links to the tracker's records, which aidd never calls
    "risks",  # the four RAID lists are "kept current here". They let through an added item and an edit. They take back a removed item
    "assumptions",  # and an item moved to `accepted`, which the schema defines as a person accepting it as it stands
    "issues",
    "dependencies",
)
# The same for one slice line. `blocked_by` and `development_team` leave the line when a slice starts, and `drafted_in` names a draft that
# still goes through Spec approval. `merged_in` lets through a first commit id that the default branch holds, which the delegate checks
# (`new_merged_in`), and takes back a change or a removal: an id that names no commit would make an unbuilt slice read as done.
PLANNED_SPEC_KEPT = ("blocked_by", "development_team", "merged_in", "drafted_in")
RAID = ("risks", "assumptions", "issues", "dependencies")
# The approved version's mark that the body now differs from the approved body, set where only the file's current text is at hand
# (`intent_checks.approved_version`), so `aidd validate` and `aidd status` read the body through the same owner.
BODY_CHANGED = "_body_changed"
_BODY = ("body",)  # a key no front matter can hold, so the body never hides a key of that name


def approval_body(body: str) -> str:
    """The whole body, with its line endings read as one: no section of it is one an agent keeps writing."""
    return body.replace("\r\n", "\n").rstrip()


def _without(item: object, keys: tuple[str, ...]) -> object:
    """A mapping without `keys`; anything else, such as a field of the wrong shape, as it is, so that it counts."""
    return {k: v for k, v in item.items() if k not in keys} if isinstance(item, dict) else item


def approval_view(data: dict, body: str | None = None) -> dict:
    """What a person approved in an Intent: its front matter in today's shape except AGENT_KEPT and each slice's PLANNED_SPEC_KEPT, the
    way it reaches users with the schema's default when a file sets none, and the whole body when it is given.
    Raises `retired_names.Refused` for a shape the upgrade leaves for a person."""
    view = {k: v for k, v in old_shape.todays_shape(data).items() if k not in AGENT_KEPT and k != BODY_CHANGED}
    view.setdefault("reaches", "incremental")
    if isinstance(view.get("phases"), list):
        view["phases"] = [
            {**p, "specs": [_without(s, PLANNED_SPEC_KEPT) for s in p["specs"]]} if isinstance(p, dict) and isinstance(p.get("specs"), list) else p
            for p in view["phases"]
        ]
    if isinstance(view.get("success_criteria"), list):
        view["success_criteria"] = [_without_draft(c) for c in view["success_criteria"]]
    if body is not None:
        view[_BODY] = approval_body(body)
    return view


def _is_draft(result: object) -> bool:
    """Whether a criterion's `result` is a draft: a mapping with no `approval`."""
    return isinstance(result, dict) and "approval" not in result


def _without_draft(criterion: object) -> object:
    """A criterion without its `result` while that result is a draft; anything else as it is, so that it counts."""
    if isinstance(criterion, dict) and _is_draft(criterion.get("result")):
        return {k: v for k, v in criterion.items() if k != "result"}
    return criterion


def _list(value: object) -> list:
    return value if isinstance(value, list) else []


def _planned_spec_lines(data: dict) -> dict[str, dict]:
    return {str(s["id"]): s for p in phases_of(data) for s in planned_specs_of(p)}


def new_merged_in(then: dict, now: dict) -> list[str]:
    """The commit ids `now` records as a slice's `merged_in` that `then` holds for no slice: the ones whose commit the caller must
    find on the default branch, since only that makes the slice done. A slice with a `repo` is left out: its commit lies in another
    repository, which aidd reads none of, so its `merged_in` is kept as written."""
    was = {i: s.get("merged_in") for i, s in _planned_spec_lines(old_shape.todays_shape(then)).items()}
    lines = _planned_spec_lines(old_shape.todays_shape(now)).items()
    return [str(s["merged_in"]) for i, s in lines if s.get("merged_in") and not was.get(i) and not s.get("repo")]


def _kept_changes(then: dict, now: dict) -> list[str]:
    """What a person approved that lies inside a kept field, which a change takes back: a RAID item removed or moved to `accepted`, a
    result the approved version holds changed or removed, a blocker removed, a slice's `merged_in` changed or removed, and a kept
    value that fails its schema (it would read as no value, so anything could hide in it). Each is named by its field."""
    names = []
    for key in RAID:
        was, is_ = [i for i in _list(then.get(key)) if isinstance(i, dict)], [i for i in _list(now.get(key)) if isinstance(i, dict)]
        accepted = {str(i.get("id")) for i in was if i.get("status") == "accepted"}
        removed = len(_list(now.get(key))) < len(_list(then.get(key))) or {str(i.get("id")) for i in was} - {str(i.get("id")) for i in is_}
        if removed or any(i.get("status") == "accepted" and str(i.get("id")) not in accepted for i in is_):
            names.append(key)
    now_results = {c["id"]: c.get("result") for c in criteria.criteria_of(now)}
    drafts = {c["id"]: c["result"] for c in criteria.criteria_of(then) if _is_draft(c.get("result"))}
    if any(now_results.get(i) != r for i, r in drafts.items()):
        names.append("result")
    if {str(i) for i in _list(then.get("blocked_by"))} - {str(i) for i in _list(now.get("blocked_by"))}:
        names.append("blocked_by")
    now_lines = _planned_spec_lines(now)
    if any(s.get("merged_in") and now_lines.get(i, {}).get("merged_in") != s["merged_in"] for i, s in _planned_spec_lines(then).items()):
        names.append("merged_in")
    for error in json_schema.validate(now, "intent.schema.json"):
        if (named := re.match(r"\$\.(\w+)", error)) and named.group(1) in AGENT_KEPT and now.get(named.group(1)) != then.get(named.group(1)):
            names.append(named.group(1))
        if re.match(r"\$\.success_criteria\[\d+\]\.result\b", error):  # a draft that fails its schema would hide anything
            names.append("result")
        if (line := re.search(r"\.specs\[\d+\]\.(\w+)", error)) and line.group(1) in PLANNED_SPEC_KEPT:
            names.append(line.group(1))
    return names


def approved_changes(then: dict, now: dict, then_body: str | None = None, now_body: str | None = None) -> list[str]:
    """The names of what differs between the Intent a person approved (`then`) and `now`: each front matter key that differs, as its
    name, `specs` for a difference in the set of planned Spec ids, `body` when both bodies are given and differ (or `then` says its body
    differs), and what `_kept_changes` takes back of the kept fields. Empty when nothing does. A key one side lacks counts, so no
    field is covered by being named. Raises `retired_names.Refused` for a shape the upgrade leaves for a person: what it covers
    cannot be compared with a guess."""
    before, after = approval_view(then, then_body), approval_view(now, now_body)
    names = [("body" if k == _BODY else k) for k in dict.fromkeys([*before, *after]) if k != "phases" and before.get(k) != after.get(k)]
    names += ["specs"] * (set(planned_spec_ids(then)) != set(planned_spec_ids(now)))
    names += ["phases"] * (before.get("phases") != after.get("phases") and "specs" not in names)
    names += ["body"] * bool(then.get(BODY_CHANGED))
    names += [BODY_CHANGED] * (BODY_CHANGED in now and now[BODY_CHANGED] != then.get(BODY_CHANGED))  # the mark is no key a file may hold
    names += _kept_changes(old_shape.todays_shape(then), old_shape.todays_shape(now))
    return list(dict.fromkeys(names))


def changes_since(then: dict, now: dict) -> list[str]:
    """What changed in the front matter of an Intent since the version a person approved (`then`), each as a phrase: the slices
    added or removed, a new `outcome`, and any other covered key by its name (`approved_changes`). Empty when nothing did. Both versions
    read in today's shape, so an `aidd upgrade` between them (a `slices` list that became one phase) changes nothing."""
    try:
        names = approved_changes(then, now)
        before, after = planned_spec_ids(old_shape.todays_shape(then)), planned_spec_ids(old_shape.todays_shape(now))
    except retired_names.Refused as exc:  # a version that cannot be read cannot show that nothing changed
        return [f"it cannot be read in today's shape ({exc})"]
    added, removed = [s for s in after if s not in before], [s for s in before if s not in after]
    out = [f"slice{'s' if len(added) > 1 else ''} {', '.join(added)} added"] if added else []
    out += [f"slice{'s' if len(removed) > 1 else ''} {', '.join(removed)} removed"] if removed else []
    return out + [f"its {n.replace('_', ' ')} changed" for n in names if n != "specs"]


@functools.cache
def stages() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """The stages, in order, each (name, its steps), from `graph.stages` in `schemas/roles.json`."""
    return tuple((str(s["name"]), tuple(str(x) for x in s["steps"])) for s in knowledge.roles()["graph"]["stages"])


def stage_of_step(step: str) -> str:
    """The stage that groups loop step `step`, or "" when no stage does."""
    return next((name for name, steps in stages() if step in steps), "")


def _window_end(data: dict) -> dt.date | None:
    """The last day of a released change's observe window: the release day plus `observe.window`, rounded up to a day."""
    released = status.released_on(data)
    m = _WINDOW.match(str((data.get("observe") or {}).get("window") or ""))
    if released is None or not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    return released + dt.timedelta(days=n if unit == "d" else -(-n // 24) if unit == "h" else -(-n // 1440))


def observing(data: dict, today: dt.date) -> bool:
    """Whether a merged change is still in Roll out: it has an observe window and no recorded result, and the window
    has not passed since the release (or the release is still to come)."""
    out = data["outcome"] if isinstance(data.get("outcome"), dict) else {}
    if not (data.get("observe") or {}).get("window") or out.get("observe_result") or out.get("rolled_back"):
        return False
    end = _window_end(data)
    return end is None or today <= end


def spec_step_at(data: dict, state: str, today: dt.date) -> str:
    """The loop step a Spec in `state` stands at, from its file alone: Specify while a draft or ready, Implement once
    approved and while a Task is not done, Verify once every Task is done, Merge in review, Roll out while a merged
    change's observe window is open, then Learn. "" for a cancelled Spec, which stands in no step."""
    if state in status.SPECIFYING:
        return "Specify"
    if state == "approved":
        return "Implement"
    if state == "in_progress":
        tasks = [t for t in data.get("tasks") or [] if isinstance(t, dict)]
        return "Verify" if tasks and all(t.get("done") is True for t in tasks) else "Implement"
    if state == "in_review":
        return "Merge"
    if state == "done":
        return "Roll out" if observing(data, today) else "Learn"
    if state == "rolled_back":
        return "Learn"
    return ""


def spec_stage(data: dict, state: str, today: dt.date) -> str:
    """The stage a Spec in `state` stands in, or "" for a cancelled one. A Spec in review waits at Merge approval, so it
    stands in the stage that gate ends, as a Spec waiting at Spec approval stands in Design."""
    step = spec_step_at(data, state, today)
    if state == "in_review":
        return next((str(g["stage"]) for g in knowledge.roles()["graph"]["gates"] if g["before"] == step), "")
    return stage_of_step(step) if step else ""


def planned_spec_status(line: dict, specs: dict[str, str]) -> str:
    """A slice's status: its Spec's, once the Spec file exists; else `done` once its line records `merged_in`; else
    planned."""
    sid = str(line.get("id"))
    if sid in specs:
        return specs[sid]
    return "done" if line.get("merged_in") else PLANNED


def intent_statuses(
    items: list[dict], specs: dict[str, str], approved: frozenset[str] = frozenset()
) -> tuple[dict[str, str], dict[str, tuple[int, int]], dict[str, list[str]]]:
    """Every Intent's status from its children's, added to `specs` (the Specs' statuses by id), with each slice that has
    no Spec file by its line's status; with each Intent's progress (children finished, of all) and its children's ids:
    its slices, in phase order, then each other Spec that names it as `parent`. `approved` holds the ids of the Intents
    whose approval holds, which an Intent with no started slice reads as `approved`."""
    states = dict(specs)
    children: dict[str, list[str]] = {}
    for d in items:
        if d.get("type") == "intent" and d.get("id"):
            for p in phases_of(d):
                for s in planned_specs_of(p):
                    states.setdefault(str(s["id"]), planned_spec_status(s, specs))
            children[str(d["id"])] = planned_spec_ids(d)
    for d in items:
        if d.get("parent") and d.get("id") and str(d["id"]) not in children.get(str(d["parent"]), []):
            children.setdefault(str(d["parent"]), []).append(str(d["id"]))
    progress: dict[str, tuple[int, int]] = {}
    for d in items:
        if d.get("type") != "intent" or not d.get("id"):
            continue
        cid = str(d["id"])
        kids = [states.get(c, "draft") for c in children.get(cid, [])]
        states[cid] = status.intent_status(d, kids, cid in approved)
        if kids:
            progress[cid] = (sum(1 for k in kids if status.finished(k)), len(kids))
    return states, progress, children


def phase_view(data: dict, specs: dict[str, str], spec_data: dict[str, dict], today: dt.date) -> list[dict]:
    """The Intent's phases as `aidd status --json` gives them: each `{id?, name?, due?, specs}`, and each slice with
    its status and, once it has one, its stage."""
    out = []
    for p in phases_of(data):
        lines = []
        for s in planned_specs_of(p):
            sid, state = str(s["id"]), planned_spec_status(s, specs)
            entry: dict = {"id": sid, "title": str(s.get("title") or ""), "status": state}
            stage = stage_of_step("Plan") if state == PLANNED else spec_stage(spec_data.get(sid, {}), state, today) if sid in spec_data else ""
            if stage:
                entry["stage"] = stage
            lines.append(entry)
        phase: dict = {k: str(p[k]) for k in ("id", "name", "due", "finished_on") if p.get(k)}
        out.append({**phase, "specs": lines})
    return out


def holder_of(items: list[dict], oid: str) -> str | None:
    """The id of the Intent among the status `items` whose slice line holds `oid`, a Spec nobody started, or None."""
    for item in items:
        if any(s["id"] == oid for phase in item.get("phases") or [] for s in phase["specs"]):
            return str(item["id"])
    return None


def current_phase(phases: list[dict]) -> int:
    """The index of the first phase with a slice not yet finished, or -1 when every slice is."""
    return next((i for i, p in enumerate(phases) if any(not status.finished(s["status"]) for s in p["specs"])), -1)


def ready_planned_specs(data: dict, states: dict[str, str], specs: dict[str, str]) -> list[str]:
    """The slices whose work may start: no Spec file yet, not merged, and every item they wait for merged or ended, in
    phase order."""
    out = []
    for p in phases_of(data):
        for s in planned_specs_of(p):
            if planned_spec_status(s, specs) == PLANNED and all(status.status_unblocks(states.get(w, "draft")) for w in planned_spec_blocked_by(s)):
                out.append(str(s["id"]))
    return out


def phase_line(item: dict) -> str:
    """The progress line `aidd status` prints under an Intent: its current phase, each slice there with its stage, and
    what is planned after it, such as `Phase 1 · Walking skeleton: SPEC-31 in Test, SPEC-32 planned · 3 planned in 1
    more phase`. The phase before it shows finished, as `Phase 1 · Walking skeleton: done 14 Nov`, and when every
    phase is finished, the last one does. "" when there is no phase."""
    phases = item.get("phases") or []
    at = current_phase(phases)
    if at < 0:
        return finished_phase(phases, len(phases) - 1) if phases and phases[-1]["specs"] else ""
    here = phases[at]
    shown = []
    for s in here["specs"]:
        if s["status"] == PLANNED:
            shown.append(f"{s['id']} planned")
        elif s.get("stage") and not status.finished(s["status"]):
            shown.append(f"{s['id']} in {s['stage']}")
    later = [s for p in phases[at + 1 :] for s in p["specs"] if s["status"] == PLANNED]
    more = len([p for p in phases[at + 1 :] if any(s["status"] == PLANNED for s in p["specs"])])
    tail = f" · {len(later)} planned in {more} more phase{'' if more == 1 else 's'}" if later else ""
    head = f"{phase_label(phases, at)}: " if phase_label(phases, at) else ""
    before = f"{finished_phase(phases, at - 1)} · " if at > 0 else ""
    return f"{before}{head}{', '.join(shown) or 'every slice started'}{tail}"


_NOT_A_NAME = "cannot be a branch name (git refuses ':', '..', and a '.lock' ending), so give it another id"


def branch_lines(item: dict) -> list[str]:
    """The lines `aidd status` prints under a `batched` Intent: its one pending Merge approval, then a line for each Spec
    with a `branch_state` that says where it stands on `intent/<ID>`, and what to do when a branch is missing. [] for any
    other Intent."""
    here, state, lines = f"intent/{item['id']}", item.get("branch_state"), []
    if state == "unmerged":
        lines.append(f"  Merge approval pending for {here}: its Specs count as done, and nothing is shipped until it lands on the default branch")
    behind = {
        "missing": f"no {here} branch: cut it from the default branch",
        "remote_only": f"no local {here}: check out origin's, or cut it from the default branch",
        "invalid_name": f"{here} {_NOT_A_NAME}",
    }.get(str(state), "")
    for p in item.get("phases") or []:
        for s in p["specs"]:
            sid = s["id"]
            words = {
                "merged": f"nothing left to merge into {here}",
                "unmerged": f"waits to merge into {here}",
                "missing": f"no spec/{sid} branch: cut it from {here}",
                "remote_only": f"no local spec/{sid}: check out origin's, or cut it from {here}",
                "invalid_name": f"spec/{sid} {_NOT_A_NAME}",
                "intent_branch_missing": behind,
            }.get(s.get("branch_state", ""))
            if words:
                lines.append(f"  {sid}: {words}")
    return lines


def phase_label(phases: list[dict], at: int) -> str:
    """How a person reads phase `at`: "Phase <n> · <name>", by its place in the order; its id stays in the file and the
    JSON. "" for a phase with no id and no name, which a valid Intent has none of."""
    phase = phases[at]
    if not phase.get("id") and not phase.get("name"):
        return ""
    return " · ".join([f"Phase {at + 1}", *([str(phase["name"])] if phase.get("name") else [])])


def phase_heading(phases: list[dict], at: int) -> str:
    """Phase `at` as a page heads it: its label, then "done" and the day it finished once every slice finished or a
    person recorded `finished_on`, else the day it is due, when a person named one."""
    phase = phases[at]
    if phase.get("finished_on") or (phase["specs"] and all(status.finished(s["status"]) for s in phase["specs"])):
        return finished_phase(phases, at)
    label = phase_label(phases, at) or "One phase"
    day = timestamps.parse_date(str(phase.get("due") or ""))
    return f"{label} · due {day.day} {MONTHS[day.month - 1]}" if day else label


def finished_phase(phases: list[dict], at: int) -> str:
    """A finished phase, such as "Phase 2 · Tenancy: done 14 Nov", with the day its `finished_on` names."""
    day = timestamps.parse_date(str(phases[at].get("finished_on") or ""))
    label = phase_label(phases, at)
    return f"{label + ': ' if label else ''}done{f' {day.day} {MONTHS[day.month - 1]}' if day else ''}"
