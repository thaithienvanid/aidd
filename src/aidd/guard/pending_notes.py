"""A note for the agent that its harness dropped, kept until a hook can deliver it.

Grok Build discards an allowing UserPromptSubmit hook's output, so the line that says aidd recorded the person's
typed decision (`approve SPEC-1`) never reaches the model, which then asks the person again. The prompt hook keeps
that line here, per session, in the git directory (never the working tree), and the next PreToolUse or Stop hook of
the same session delivers it once, through a channel the harness shows the model.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from aidd import config

NOTES_FILE = "pending-notes.json"
MAX_SESSIONS = 50  # a session that never calls a tool or stops leaves its note; the oldest go first


def _path(root: str | Path) -> Path:
    return config.state_dir(root) / NOTES_FILE


def _read(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(data, dict) else {}


def _write(path: Path, notes: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}")
    tmp.write_text(json.dumps(notes), encoding="utf-8")
    os.replace(tmp, path)


def keep(root: str | Path, session_id: str, note: str) -> None:
    """Keep `note` for the session's next hook that can deliver it; a newer note replaces an older one."""
    if not session_id:
        return
    path = _path(root)
    notes = _read(path)
    notes.pop(session_id, None)
    notes[session_id] = note
    _write(path, dict(list(notes.items())[-MAX_SESSIONS:]))


def take(root: str | Path, session_id: object) -> str | None:
    """The session's kept note, removed as it is read; None when there is none."""
    if not isinstance(session_id, str) or not session_id:
        return None
    path = _path(root)
    notes = _read(path)
    note = notes.pop(session_id, None)
    if note is not None:
        _write(path, notes)
    return note
