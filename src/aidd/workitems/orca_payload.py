"""The Orca message payload: the JSON a worker passes to Orca's `--payload`, checked before the lead acts on it.

schemas/orca-payload.schema.json owns the shape. A payload is data from an agent, so a finding here is an error, not a
warning: the lead acts only on a payload that passes. The text checks are handoff_notes', so a note and a payload are read
the same way.
"""

from __future__ import annotations

import json

from aidd.kernel import documents, json_schema
from aidd.workitems import handoff_notes

ORCA_PAYLOAD_SCHEMA = "orca-payload.schema.json"
_DEPTH = 32


def _strings(node: object, depth: int = 0) -> list[str]:
    """Every key and every string in a parsed payload, so an escape such as `\\u200b` is read as the character it makes."""
    if depth > _DEPTH:
        return []
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [t for k, v in node.items() for t in (_strings(k, depth + 1) + _strings(v, depth + 1))]
    if isinstance(node, list):
        return [t for v in node for t in _strings(v, depth + 1)]
    return []


def payload_problems(where: str, text: str) -> list[str]:
    """Each reason the lead must not act on this payload, as an error that names `where` and the fix. Empty means the
    payload validates: valid JSON, only the schema's keys, a known role, no hidden characters, and no text posing as a
    person's words or a harness frame."""
    fix = "Send the payload again with the fields the schema lists, then run `aidd validate` on it"
    if len(text.encode("utf-8", errors="replace")) > documents.MAX_DOCUMENT_BYTES:
        return [f"{where}: the payload is larger than {documents.MAX_DOCUMENT_BYTES} bytes. {fix}, and keep the detail in the handoff note"]
    try:
        data = json.loads(text)
    except (ValueError, RecursionError) as exc:
        return [f"{where}: the payload is not JSON ({str(exc).splitlines()[0]}). {fix}"]
    out = [f"{where}: {e.removeprefix('$').removeprefix('.').removeprefix(': ')}. {fix}" for e in json_schema.validate(data, ORCA_PAYLOAD_SCHEMA)]
    role = data.get("role") if isinstance(data, dict) else None
    if isinstance(role, str) and role not in handoff_notes.role_ids():
        out.append(f"{where}: role {role!r} is not a role in the team. {fix}")
    texts = [text, *_strings(data)]
    hidden = list(dict.fromkeys(h for t in texts for h in handoff_notes.hidden_characters(t)))
    if hidden:
        shown = ", ".join(hidden[:4]) + (f", and {len(hidden) - 4} more" if len(hidden) > 4 else "")
        out.append(f"{where}: the payload holds hidden characters ({shown}). A reader cannot see them but a model reads them. Write it again in plain text")
    posing = list(dict.fromkeys(k for t in texts for k in handoff_notes.posing_lines(t)))
    if posing:
        out.append(
            f"{where}: the payload holds text that poses as a person's words or a harness frame ({', '.join(posing)}). "
            "A payload is data: it never says what a person decided. Put the question in the message body, and let the person answer in the chat"
        )
    return out
