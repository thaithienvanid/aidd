"""Status: what each work item's front matter says, read the same way everywhere, and the facts built on it.

A Spec's `status` is stored, and the agent sets it as the work moves: `draft` while it is written, `ready` once it
asks for Spec approval, `approved` on the person's yes (with `approved_by` and `approved_at`), `in_progress`,
`in_review`, and `done` once it merged; `rolled_back` and `cancelled` end it. A missing status reads as `draft`.
Blocked is a flag, not a status: `waiting_on` names a wait, a `blocked_by` item is not finished, or a Task used its
retries. Nothing here is evidence.
"""

from __future__ import annotations

import datetime as dt
import re

from aidd import config
from aidd.kernel import timestamps

# Each set of statuses below is a row of `x-sets` in the status table of its type (`config.status_table`), and the table
# also holds the initial status and every move (`x-transitions`). No module keeps a list of statuses of its own.
SPEC_STATUSES = tuple(config.status_table("spec")["enum"])
# At or past Spec approval.
PAST_APPROVAL = config.status_set("spec", "past_approval")
# Before Implement: the Design stage, where the Spec's tests are expected to fail on the head.
BEFORE_IMPLEMENT = config.status_set("spec", "before_implement")
# Specify: the Spec is written, or waits for approval.
SPECIFYING = config.status_set("spec", "specifying")
# Past implementation: every Task's work is built.
BUILT = config.status_set("spec", "built")
# The work ended. It counts toward its Intent's progress, and what another item's blocked_by waits for (the work merged,
# or ended).
TERMINAL = config.status_set("spec", "ended")
# Statuses whose work can still be blocked; once in review, the work is built.
CAN_WAIT = config.status_set("spec", "can_wait")
# A child whose work started, whatever its type, so the Intent that holds it is active.
STARTED = frozenset().union(*(config.status_set(t, "started") for t in config.types_of_form("work_item") if "started" in config.status_table(t)["x-sets"]))
# Once the change reached production: what the hypothesis is measured after.
LANDED_STATUSES = config.status_set("spec", "landed")
# Ended with no change in production: a rollback, or a cancel.
ENDED_UNLANDED = TERMINAL - LANDED_STATUSES
# Approved and not ended: the Spec's tests, its design files, and its Tasks' scopes are frozen, and its change is open.
IN_FLIGHT = PAST_APPROVAL - TERMINAL
# Implement: the Tasks are built, one by one.
IMPLEMENTING = config.status_set("spec", "implementing")
# The Spec asked for approval: the documents it folds into are due.
ASKED = config.status_set("spec", "asked")
IN_THE_SRS = config.status_set("spec", "in_the_srs")
# From review on: a person who accepts by hand has a record that lists the Spec's ids.
ACCEPTANCE_DUE = config.status_set("spec", "acceptance_due")
# Work an agent suggested needs no person's triage here; at every other status it must have been accepted.
WITHOUT_TRIAGE = config.status_set("spec", "without_triage")
# Where a Spec waits for a person's yes to Spec approval: a status from which a person's move reaches one at or past approval.
ASKS_APPROVAL = frozenset(
    s for m in config.status_transitions("spec") if m["who"] == "person" and m["to"] in PAST_APPROVAL for s in m["from"] if s not in PAST_APPROVAL
)
# An Intent's statuses: the ones a person records (done or cancelled), the one that needs every child finished, and the
# ones whose work can still be blocked.
INTENT_STATUSES = tuple(config.status_table("intent")["enum"])
INTENT_ENDED = config.status_set("intent", "ended")
INTENT_NEEDS_FINISHED_CHILDREN = config.status_set("intent", "needs_finished_children")
INTENT_CAN_WAIT = config.status_set("intent", "can_wait")
PRIORITIES = ("urgent", "high", "medium", "low")

_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_WINDOW = re.compile(r"^([0-9]+)([mhd])$")


def stored_status(data: dict) -> str | None:
    """The stored status (None when there is none)."""
    raw = data.get("status")
    return raw if isinstance(raw, str) else None


def spec_status(data: dict) -> str:
    """A Spec's status: what it stores, `cancelled` when a person's triage declined it, else the status a new Spec starts in."""
    if (data.get("triage") or {}).get("decision") == "declined":
        return "cancelled"
    s = stored_status(data)
    return s if s is not None and s in SPEC_STATUSES else config.initial_status("spec")


def _tasks(data: dict) -> list[dict]:
    return [t for t in data.get("tasks") or [] if isinstance(t, dict)]


# What a template leaves for a person or an agent to fill in.
PLACEHOLDER = "TODO"


def is_planned(data: dict, status: str) -> bool:
    """Whether a Spec is planned and not started: a draft whose every Task still holds a placeholder, in its title or its
    scope, so nobody has cut it into work yet. A Spec outline from a plan reads so until Specify writes its Tasks; a
    plan may already name a Task's likely scope, which the route advice reads."""
    if status != "draft":
        return False
    return all(PLACEHOLDER in str(t.get("title")) or PLACEHOLDER in str(t.get("scope")) for t in _tasks(data))


def hypothesis_due(data: dict) -> dt.date | None:
    """When the Spec's hypothesis is due to be measured: the latest date its own text names ("... by 2026-12-31"),
    else the release (`outcome.released_on`) plus the observe window. None when neither says."""
    named = [d for d in (timestamps.parse_date(m) for m in _ISO_DATE.findall(str(data.get("hypothesis") or ""))) if d]
    if named:
        return max(named)
    released = timestamps.parse_date((data.get("outcome") or {}).get("released_on") or "")
    if released is None:
        return None
    m = _WINDOW.match(str((data.get("observe") or {}).get("window") or ""))
    if not m:
        return released
    n, unit = int(m.group(1)), m.group(2)
    days = n if unit == "d" else -(-n // 24) if unit == "h" else -(-n // 1440)
    return released + dt.timedelta(days=days)


def outcome_due(data: dict, status: str, today: dt.date) -> dt.date | None:
    """The date a merged Spec's hypothesis was due, when it has passed and nobody recorded `outcome.result`; else None."""
    out = data.get("outcome") or {}
    if not data.get("hypothesis") or out.get("result"):
        return None
    if status not in LANDED_STATUSES and not (out.get("released_on") and status not in ENDED_UNLANDED):
        return None
    due = hypothesis_due(data)
    return due if due is not None and due < today else None


def retries_used(data: dict, max_retries: int) -> list[str]:
    """The Tasks that used their `max_retries` (the config's `limits.max_task_retries`)."""
    return [str(t.get("id")) for t in _tasks(data) if int(t.get("retry_count") or 0) >= max_retries]


def blocked_reasons(data: dict, status: str, max_retries: int, waits: list[str] | tuple[str, ...] = ()) -> list[str]:
    """Why the item is blocked, or [] when it is not: waiting_on names a wait, blocked_by work is unfinished, or a Task
    used its retries. Only open work can be blocked, and a draft or ready Spec is never blocked by `waits`, which hold
    Implement."""
    if status not in CAN_WAIT and status not in INTENT_CAN_WAIT:
        return []
    out = []
    if str(data.get("waiting_on") or "").strip():
        out.append(str(data["waiting_on"]))
    out += [f"{t} used its {max_retries} retries; a person re-plans it" for t in retries_used(data, max_retries)]
    if waits and status not in SPECIFYING:  # work it is blocked_by holds Implement, never Specify
        out.append(f"blocked by {', '.join(waits)}")
    return out


def task_states(data: dict, status: str, max_retries: int) -> list[dict]:
    """Each Task with its state: `done` (recorded, or the Spec is past implementation), `stopped` (it used its
    retries), `blocked` (a Task it depends on is not done, or the Spec waits for approval), else `todo`."""
    tasks = _tasks(data)
    done = {str(t.get("id")) for t in tasks if status in BUILT or t.get("done") is True}
    out = []
    for t in tasks:
        tid = str(t.get("id"))
        task: dict = {"id": t.get("id"), "title": t.get("title"), "scope": list(t.get("scope", []) or []), "depends_on": list(t.get("depends_on", []) or [])}
        pending = [d for d in task["depends_on"] if d not in done]
        why = ""
        if tid in done:
            state = "done"
        elif status == "cancelled":
            state, why = "blocked", "the Spec is cancelled"
        elif status in SPECIFYING:
            state, why = "blocked", "the Spec waits for its approval; no Task starts before it"
        elif int(t.get("retry_count") or 0) >= max_retries:
            state, why = "stopped", f"used its {max_retries} retries: a person re-plans it"
        elif pending:
            state, why = "blocked", f"waits for {', '.join(pending)} to be done"
        else:
            state = "todo"
        task["status"] = state
        if why:
            task["why"] = why
        out.append(task)
    return out


def intent_status(data: dict, children: list[str]) -> str:
    """An Intent's status from its children's (its slices' and its Specs'): done or cancelled when a person recorded it
    (a `go_no_go` of `no_go` is cancelled), active once any child started, else draft."""
    s = stored_status(data)
    if s in INTENT_ENDED:
        return s
    if (data.get("go_no_go") or {}).get("decision") == "no_go":
        return "cancelled"
    if not children:
        return s if s is not None and s in INTENT_STATUSES else config.initial_status("intent")
    return "active" if any(c in STARTED for c in children) else "draft"


def finished(status: str) -> bool:
    """Whether a child counts toward its Intent's progress: it ended (done, rolled back, or cancelled)."""
    return status in TERMINAL


def status_unblocks(status: str) -> bool:
    """Whether an item another one is blocked_by lets it go: the work merged, or ended."""
    return status in TERMINAL


def item_priority(data: dict, idx: dict[str, dict] | None = None) -> str:
    """The item's priority: an emergency is urgent; else its own, else its nearest parent's, else medium."""
    if data.get("route") == "emergency":
        return "urgent"
    seen: set[str] = set()
    item: dict | None = data
    while item is not None:
        if item.get("priority") in PRIORITIES:
            return str(item["priority"])
        parent = str(item.get("parent") or "")
        if not parent or parent in seen or idx is None:
            break
        seen.add(parent)
        item = idx.get(parent)
    return "medium"
