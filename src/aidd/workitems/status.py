"""Status: what each work item's front matter says, read the same way everywhere, and the facts built on it.

A Spec's `status` is stored, and the agent sets it as the work moves: `draft` while it is written, `ready` once it
asks for Spec approval, `approved` on the person's yes (with `approved_by` and `approved_at`), `in_progress`,
`in_review`, and `done` once it merged; `rolled_back` and `cancelled` end it. A missing status reads as `draft`.
Blocked is a flag, not a status: `blockers` names a wait, a `blocked_by` item is not finished, or a Task used its
retries. Nothing here is evidence.
"""

from __future__ import annotations

import datetime as dt
import re

from aidd.kernel import timestamps

SPEC = ("draft", "ready", "approved", "in_progress", "in_review", "done", "rolled_back", "cancelled")
# At or past Spec approval.
PAST_APPROVAL = frozenset({"approved", "in_progress", "in_review", "done", "rolled_back"})
# Past implementation: every Task's work is built.
BUILT = frozenset({"in_review", "done", "rolled_back"})
TERMINAL = frozenset({"done", "rolled_back", "cancelled"})
# What another item's blocked_by waits for: the work merged (or ended).
UNBLOCKS = frozenset({"done", "rolled_back", "cancelled"})
# Statuses whose work can still be blocked; once in review, the work is built.
CAN_WAIT = frozenset({"draft", "ready", "approved", "in_progress"})
STARTED = frozenset({"in_progress", "in_review", "done", "rolled_back", "active"})
# Once the change reached production: what the hypothesis is measured after.
LANDED_STATUSES = frozenset({"done"})
MAX_RETRIES = 3
PRIORITIES = ("urgent", "high", "medium", "low")

_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_WINDOW = re.compile(r"^([0-9]+)([mhd])$")


def stored_status(data: dict) -> str | None:
    """The stored status (None when there is none)."""
    raw = data.get("status")
    return raw if isinstance(raw, str) else None


def spec_status(data: dict) -> str:
    """A Spec's status: what it stores, `cancelled` when a person's triage declined it, else `draft`."""
    if (data.get("triage") or {}).get("decision") == "declined":
        return "cancelled"
    s = stored_status(data)
    return s if s in SPEC else "draft"


def _tasks(data: dict) -> list[dict]:
    return [t for t in data.get("tasks") or [] if isinstance(t, dict)]


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
    if status not in LANDED_STATUSES and not (out.get("released_on") and status not in ("rolled_back", "cancelled")):
        return None
    due = hypothesis_due(data)
    return due if due is not None and due < today else None


def retries_used(data: dict) -> list[str]:
    return [str(t.get("id")) for t in _tasks(data) if int(t.get("retry_count") or 0) >= MAX_RETRIES]


def blocked_reasons(data: dict, status: str, waits: list[str] | tuple[str, ...] = ()) -> list[str]:
    """Why the item is blocked, or [] when it is not: blockers names a wait, blocked_by work is unfinished, or a Task
    used its retries. Only open work can be blocked."""
    if status not in CAN_WAIT and status != "active":
        return []
    out = []
    if str(data.get("blockers") or "").strip():
        out.append(str(data["blockers"]))
    out += [f"{t} used its {MAX_RETRIES} retries; a person re-plans it" for t in retries_used(data)]
    if waits:
        out.append(f"blocked by {', '.join(waits)}")
    return out


def task_states(data: dict, status: str) -> list[dict]:
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
        elif status in ("draft", "ready"):
            state, why = "blocked", "the Spec waits for its approval; no Task starts before it"
        elif int(t.get("retry_count") or 0) >= MAX_RETRIES:
            state, why = "stopped", f"used its {MAX_RETRIES} retries: a person re-plans it"
        elif pending:
            state, why = "blocked", f"waits for {', '.join(pending)} to be done"
        else:
            state = "todo"
        task["status"] = state
        if why:
            task["why"] = why
        out.append(task)
    return out


def container_status(data: dict, children: list[str]) -> str:
    """An Epic's or Initiative's status: done or cancelled when a person recorded it (an Initiative's `go_no_go` of
    `no_go` is cancelled), active once any child started, else draft."""
    s = stored_status(data)
    if s in ("done", "cancelled"):
        return s
    if (data.get("go_no_go") or {}).get("decision") == "no_go":
        return "cancelled"
    if not children:
        return s or "draft"
    return "active" if any(c in STARTED for c in children) else "draft"


def container_statuses(items: list[dict], specs: dict[str, str]) -> tuple[dict[str, str], dict[str, tuple[int, int]], dict[str, list[str]]]:
    """Every Epic's and Initiative's status from its children's, added to `specs` (the Specs' statuses by id); with
    each container's progress (children finished, of all) and its children's ids."""
    status = dict(specs)
    children: dict[str, list[str]] = {}
    for d in items:
        if d.get("parent") and d.get("id"):
            children.setdefault(str(d["parent"]), []).append(str(d["id"]))
    progress: dict[str, tuple[int, int]] = {}
    for item_type in ("epic", "initiative"):
        for d in items:
            if d.get("type") != item_type or not d.get("id"):
                continue
            cid = str(d["id"])
            kids = [status.get(c, "draft") for c in children.get(cid, [])]
            status[cid] = container_status(d, kids)
            if kids:
                progress[cid] = (sum(1 for k in kids if finished(k)), len(kids))
    return status, progress, children


def finished(status: str) -> bool:
    """Whether a child counts toward its container's progress: it ended (done, rolled back, or cancelled)."""
    return status in TERMINAL


def status_unblocks(status: str) -> bool:
    """Whether an item another one is blocked_by lets it go: the work merged, or ended."""
    return status in UNBLOCKS


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
