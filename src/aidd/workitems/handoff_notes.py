"""The handoff note: the `aidd-handoff` block a role ends each run with, the latest one a document holds, and what it asks a person for."""

from __future__ import annotations

import functools
import re

from aidd.kernel import documents, resources

# Approvals that a handoff note must not name as its `next`. The Approver inbox follows the derived status, so a note
# names the role that takes the work, and `aidd validate` warns about one of these.
APPROVAL_STEPS = ("spec-approval", "merge-approval")
HANDOFF_KEYS = ("done", "next", "needs", "stopped_at")
HANDOFF_OPTIONAL = ("spend", "status", "asked", "decided")
HANDOFF_FENCE = re.compile(r"^```aidd-handoff[ \t]*\r?\n(.*?)^```[ \t]*$", re.S | re.M)


@functools.cache
def role_ids() -> frozenset[str]:
    return frozenset(resources.load_json("roles.json")["roles"])


def handoff_blocks(text: str) -> list[tuple[dict | None, str]]:
    """Every ```aidd-handoff block in a document, in order: (its YAML as a dict, or None, and the parse error)."""
    out: list[tuple[dict | None, str]] = []
    for m in HANDOFF_FENCE.finditer(text):
        try:
            out.append((documents.parse_yaml(m.group(1), "aidd-handoff block"), ""))
        except documents.DocumentError as exc:
            out.append((None, str(exc)))
    return out


def latest_handoff(text: str) -> dict | None:
    """The last well-formed handoff note in the document, or None."""
    notes = [h for h, _ in handoff_blocks(text) if h is not None and isinstance(h.get("next"), str)]
    return notes[-1] if notes else None


def team_decisions(text: str) -> list[str]:
    """Every decision the team recorded in a document's handoff notes (`decided`), oldest first, each once: what it
    chose, and the standard, rule, or default that settled it. A report for the person, never evidence."""
    out: list[str] = []
    for note, _ in handoff_blocks(text):
        raw = (note or {}).get("decided")
        for item in raw if isinstance(raw, list) else [raw]:
            text_item = " ".join(str(item or "").split())
            if text_item and text_item.lower() not in ("none", "-") and text_item not in out:
                out.append(text_item[:300])
    return out


def needs(note: dict | None, status: str | None = None) -> list[str]:
    """What the note asks a person for; "none" and blanks ask for nothing. A note that records the `status` it was
    written in asks only while the item is still in it: once the work moved on, the question is stale."""
    if note and status and isinstance(note.get("status"), str) and note["status"] != status:
        return []
    raw = (note or {}).get("needs")
    items = raw if isinstance(raw, list) else [raw]
    return [str(x).strip() for x in items if str(x or "").strip() and str(x).strip().lower() not in ("none", "nothing", "n/a", "-")]


def handoff_counts(text: str) -> tuple[int, int]:
    """(notes, broken): every handoff note in a document, and those the next step cannot use: not YAML, a key missing,
    a `next` that is no role, or a status that is not a Spec status (keys aidd does not read do not break a note)."""
    from aidd.workitems.derived_status import SPEC

    blocks = handoff_blocks(text)
    broken = sum(
        1
        for note, _ in blocks
        if note is None
        or any(k not in note for k in HANDOFF_KEYS)
        or not isinstance(note.get("next"), str)
        or note["next"] not in role_ids()
        or ("status" in note and note["status"] not in SPEC)
    )
    return len(blocks), broken


def handoff_warnings(where: str, text: str) -> list[str]:
    """`aidd validate` warnings for handoff notes a reader cannot use: bad YAML, a missing key, a `next` that is not
    a role (an approval is not a role: the Approver inbox follows the derived status), or an unknown `status`."""
    from aidd.workitems.derived_status import SPEC

    out = []
    for i, (note, err) in enumerate(handoff_blocks(text), 1):
        if note is None:
            out.append(f"warning: {where}: handoff note {i} is not YAML ({err.split(': ', 1)[-1]})")
            continue
        missing = [k for k in HANDOFF_KEYS if k not in note]
        unknown = sorted(set(note) - set(HANDOFF_KEYS) - set(HANDOFF_OPTIONAL))
        if missing:
            out.append(f"warning: {where}: handoff note {i} has no {', '.join(missing)}")
        if unknown:
            out.append(f"warning: {where}: handoff note {i} has keys aidd does not read: {', '.join(unknown)}")
        nxt = note.get("next")
        if nxt in APPROVAL_STEPS:
            out.append(
                f"warning: {where}: handoff note {i}: next {nxt!r} is an approval, not a role. aidd puts the Spec in the Approver "
                "inbox from its derived status. Name the role that takes the work next"
            )
        elif "next" in note and (not isinstance(nxt, str) or nxt not in role_ids()):
            out.append(f"warning: {where}: handoff note {i}: next {nxt!r} is not a role")
        if "status" in note and note["status"] not in SPEC:
            out.append(f"warning: {where}: handoff note {i}: status {note['status']!r} is not a Spec status ({', '.join(SPEC)})")
    return out
