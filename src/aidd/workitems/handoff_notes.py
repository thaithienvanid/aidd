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


def handoff_warnings(where: str, text: str) -> list[str]:
    """`aidd validate` warnings for handoff notes a reader cannot use: bad YAML, a missing key, a `next` that is not
    a role (an approval is not a role: the person decides it), or an unknown `status`."""
    from aidd.workitems.status import SPEC

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
