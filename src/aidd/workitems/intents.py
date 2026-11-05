"""Intents: work bigger than one Spec, with its slices grouped into phases, and the stage each change stands in.

An Intent lists its slices, one line each, in `phases`, or with one phase in `slices`. A slice is a planned Spec: it
becomes a Spec file when its work starts (`aidd new spec <id>`), and until then it is a line. A slice with no Spec file
is finished once its line records `merged_in`.

A stage groups loop steps for people, in the order `loop.stages` in `schemas/roles.json` gives. A Spec stands in the
stage of the step its stored status and its Tasks put it at, read from its file alone, never from a report.
"""

from __future__ import annotations

import datetime as dt
import functools
import re

from aidd import knowledge
from aidd.kernel import timestamps
from aidd.workitems import status

# A slice's status when it has no Spec file: `planned` until its line records `merged_in`, then `done`.
PLANNED = "planned"
# How many ready slices `aidd status` names as the next to start: the lead starts two or three at a time.
READY_SHOWN = 3
# A day as a progress line says it, in English whatever the locale: "14 Nov".
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_WINDOW = re.compile(r"^([0-9]+)([mhd])$")


def phases_of(data: dict) -> list[dict]:
    """The Intent's phases, in order, each `{id, name, slices}` with what else it holds. An Intent that lists `slices`
    directly has one phase with no id or name. A field of the wrong shape counts as empty."""
    if isinstance(data.get("phases"), list):
        return [p for p in data["phases"] if isinstance(p, dict)]
    if isinstance(data.get("slices"), list):
        return [{"id": "", "name": "", "slices": data["slices"]}]
    return []


def slices_of(phase: dict) -> list[dict]:
    """A phase's slices that carry an id, in order."""
    found = phase.get("slices")
    return [s for s in found if isinstance(s, dict) and s.get("id")] if isinstance(found, list) else []


def slice_ids(data: dict) -> list[str]:
    """Every slice id the Intent lists, in phase order, once each."""
    return list(dict.fromkeys(str(s["id"]) for p in phases_of(data) for s in slices_of(p)))


def slice_lines(items: list[dict]) -> dict[str, tuple[dict, dict, dict]]:
    """Each slice by its id: (the Intent, its phase, the slice line), the first Intent that lists it."""
    out: dict[str, tuple[dict, dict, dict]] = {}
    for d in items:
        if d.get("type") != "intent":
            continue
        for p in phases_of(d):
            for s in slices_of(p):
                out.setdefault(str(s["id"]), (d, p, s))
    return out


def slice_blocked_by(line: dict) -> list[str]:
    """The ids a slice line waits for."""
    found = line.get("blocked_by")
    return [str(i) for i in found if i] if isinstance(found, list) else []


def changes_since(then: dict, now: dict) -> list[str]:
    """What changed in an Intent since the version a person agreed to (`then`): the slices added, the slices removed, and
    a new `goal`, each as a phrase. Order, names, dates, and the other slice fields never count. Empty when nothing did."""
    before, after = slice_ids(then), slice_ids(now)
    added, removed = [s for s in after if s not in before], [s for s in before if s not in after]
    out = [f"slice{'s' if len(added) > 1 else ''} {', '.join(added)} added"] if added else []
    out += [f"slice{'s' if len(removed) > 1 else ''} {', '.join(removed)} removed"] if removed else []
    return out + (["its goal changed"] if str(then.get("goal") or "") != str(now.get("goal") or "") else [])


@functools.cache
def stages() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """The stages, in order, each (name, its steps), from `loop.stages` in `schemas/roles.json`."""
    return tuple((str(s["name"]), tuple(str(x) for x in s["steps"])) for s in knowledge.roles()["loop"]["stages"])


def stage_of_step(step: str) -> str:
    """The stage that groups loop step `step`, or "" when no stage does."""
    return next((name for name, steps in stages() if step in steps), "")


def _window_end(data: dict) -> dt.date | None:
    """The last day of a released change's observe window: the release day plus `observe.window`, rounded up to a day."""
    released = timestamps.parse_date(str((data.get("outcome") or {}).get("released_on") or ""))
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
    if state in ("draft", "ready"):
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
        return next((str(g["stage"]) for g in knowledge.roles()["loop"]["gates"] if g["before"] == step), "")
    return stage_of_step(step) if step else ""


def slice_status(line: dict, specs: dict[str, str]) -> str:
    """A slice's status: its Spec's, once the Spec file exists; else `done` once its line records `merged_in`; else
    planned."""
    sid = str(line.get("id"))
    if sid in specs:
        return specs[sid]
    return "done" if line.get("merged_in") else PLANNED


def intent_statuses(items: list[dict], specs: dict[str, str]) -> tuple[dict[str, str], dict[str, tuple[int, int]], dict[str, list[str]]]:
    """Every Intent's status from its children's, added to `specs` (the Specs' statuses by id), with each slice that has
    no Spec file by its line's status; with each Intent's progress (children finished, of all) and its children's ids:
    its slices, in phase order, then each other Spec that names it as `parent`."""
    states = dict(specs)
    children: dict[str, list[str]] = {}
    for d in items:
        if d.get("type") == "intent" and d.get("id"):
            for p in phases_of(d):
                for s in slices_of(p):
                    states.setdefault(str(s["id"]), slice_status(s, specs))
            children[str(d["id"])] = slice_ids(d)
    for d in items:
        if d.get("parent") and d.get("id") and str(d["id"]) not in children.get(str(d["parent"]), []):
            children.setdefault(str(d["parent"]), []).append(str(d["id"]))
    progress: dict[str, tuple[int, int]] = {}
    for d in items:
        if d.get("type") != "intent" or not d.get("id"):
            continue
        cid = str(d["id"])
        kids = [states.get(c, "draft") for c in children.get(cid, [])]
        states[cid] = status.intent_status(d, kids)
        if kids:
            progress[cid] = (sum(1 for k in kids if status.finished(k)), len(kids))
    return states, progress, children


def phase_view(data: dict, specs: dict[str, str], spec_data: dict[str, dict], today: dt.date) -> list[dict]:
    """The Intent's phases as `aidd status --json` gives them: each `{id?, name?, due?, slices}`, and each slice with
    its status and, once it has one, its stage."""
    out = []
    for p in phases_of(data):
        slices = []
        for s in slices_of(p):
            sid, state = str(s["id"]), slice_status(s, specs)
            entry: dict = {"id": sid, "title": str(s.get("title") or ""), "status": state}
            stage = stage_of_step("Plan") if state == PLANNED else spec_stage(spec_data.get(sid, {}), state, today) if sid in spec_data else ""
            if stage:
                entry["stage"] = stage
            slices.append(entry)
        phase: dict = {k: str(p[k]) for k in ("id", "name", "due", "finished_on") if p.get(k)}
        out.append({**phase, "slices": slices})
    return out


def holder_of(items: list[dict], oid: str) -> tuple[str, str] | None:
    """The Intent among the status `items` that holds an id no item carries, as (its id, "a phase" or "a slice"): an Epic
    an older aidd wrote is a phase now, and a Spec nobody started is a slice line. None when no Intent holds it."""
    for item in items:
        for phase in item.get("phases") or []:
            if phase.get("id") == oid:
                return str(item["id"]), "a phase"
            if any(s["id"] == oid for s in phase["slices"]):
                return str(item["id"]), "a slice"
    return None


def current_phase(phases: list[dict]) -> int:
    """The index of the first phase with a slice not yet finished, or -1 when every slice is."""
    return next((i for i, p in enumerate(phases) if any(not status.finished(s["status"]) for s in p["slices"])), -1)


def ready_slices(data: dict, states: dict[str, str], specs: dict[str, str]) -> list[str]:
    """The slices whose work may start: no Spec file yet, not merged, and every item they wait for merged or ended, in
    phase order."""
    out = []
    for p in phases_of(data):
        for s in slices_of(p):
            if slice_status(s, specs) == PLANNED and all(status.status_unblocks(states.get(w, "draft")) for w in slice_blocked_by(s)):
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
        return finished_phase(phases, len(phases) - 1) if phases and phases[-1]["slices"] else ""
    here = phases[at]
    shown = []
    for s in here["slices"]:
        if s["status"] == PLANNED:
            shown.append(f"{s['id']} planned")
        elif s.get("stage") and not status.finished(s["status"]):
            shown.append(f"{s['id']} in {s['stage']}")
    later = [s for p in phases[at + 1 :] for s in p["slices"] if s["status"] == PLANNED]
    more = len([p for p in phases[at + 1 :] if any(s["status"] == PLANNED for s in p["slices"])])
    tail = f" · {len(later)} planned in {more} more phase{'' if more == 1 else 's'}" if later else ""
    head = f"{phase_label(phases, at)}: " if phase_label(phases, at) else ""
    before = f"{finished_phase(phases, at - 1)} · " if at > 0 else ""
    return f"{before}{head}{', '.join(shown) or 'every slice started'}{tail}"


def phase_label(phases: list[dict], at: int) -> str:
    """How a person reads phase `at`: "Phase <n> · <name>", by its place in the order; its id stays in the file and the
    JSON. "" for an Intent with one phase listed as `slices`."""
    phase = phases[at]
    if not phase.get("id") and not phase.get("name"):
        return ""
    return " · ".join([f"Phase {at + 1}", *([str(phase["name"])] if phase.get("name") else [])])


def phase_heading(phases: list[dict], at: int) -> str:
    """Phase `at` as a page heads it: its label, then "done" and the day it finished once every slice finished or a
    person recorded `finished_on`, else the day it is due, when a person named one."""
    phase = phases[at]
    if phase.get("finished_on") or (phase["slices"] and all(status.finished(s["status"]) for s in phase["slices"])):
        return finished_phase(phases, at)
    label = phase_label(phases, at) or "One phase"
    day = timestamps.parse_date(str(phase.get("due") or ""))
    return f"{label} · due {day.day} {MONTHS[day.month - 1]}" if day else label


def finished_phase(phases: list[dict], at: int) -> str:
    """A finished phase, such as "Phase 2 · Tenancy: done 14 Nov", with the day its `finished_on` names."""
    day = timestamps.parse_date(str(phases[at].get("finished_on") or ""))
    label = phase_label(phases, at)
    return f"{label + ': ' if label else ''}done{f' {day.day} {MONTHS[day.month - 1]}' if day else ''}"
