"""What the harness itself recorded about a run, read from Claude Code's session transcripts: the tokens the run used,
and when the session last did anything. An agent's own report of its spend is a claim; the transcripts are the
harness's record of each model call, the run's lead and every subagent it started.

Claude Code writes a session to `<config>/projects/<project>/<session id>.jsonl`, and each subagent of it to
`<config>/projects/<project>/<session id>/subagents/*.jsonl`. Each assistant message carries `usage`. Another harness
writes no such file: then nothing is measured, and the run falls back to what each step reported.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from aidd import config
from aidd.kernel.timestamps import parse_time

# A session id as aidd's lease takes it (lease.SESSION_ID): a plain name, never a path.
_SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
# The token kinds a run counts against `autopilot.max_tokens`. Cache reads are left out: they bill at a tenth of an
# input token, and a long run reads its cache millions of times.
COUNTED = ("input_tokens", "cache_creation_input_tokens", "output_tokens")


def transcripts(session_id: str) -> list[Path]:
    """The session's transcript and its subagents', in any project folder; [] for an id that is no plain session id."""
    if not _SESSION_ID.fullmatch(session_id):
        return []
    projects = config.claude_config_dir() / "projects"
    if not projects.is_dir():
        return []
    return sorted([*projects.glob(f"*/{session_id}.jsonl"), *projects.glob(f"*/{session_id}/subagents/*.jsonl")])


def measured_tokens(session_id: str, since: str) -> int | None:
    """The tokens the session and its subagents used from `since` on (COUNTED), or None when no transcript is found."""
    files = transcripts(session_id)
    if not files:
        return None
    start = parse_time(since)
    total = 0
    for path in files:
        try:
            with path.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"usage"' not in line:
                        continue
                    total += _counted(line, start)
        except OSError:
            continue
    return total


def _counted(line: str, start: dt.datetime | None) -> int:
    try:
        entry = json.loads(line)
    except ValueError:
        return 0
    message = entry.get("message") if isinstance(entry, dict) else None
    usage = message.get("usage") if isinstance(message, dict) else None
    if not isinstance(usage, dict):
        return 0
    when = parse_time(entry.get("timestamp"))
    if start is not None and when is not None and when < start:
        return 0
    return sum(v for k in COUNTED if isinstance(v := usage.get(k), int) and v > 0)


def last_active(session_id: str) -> dt.datetime | None:
    """When the session or one of its subagents last wrote its transcript, or None when none is found."""
    times = []
    for path in transcripts(session_id):
        try:
            times.append(dt.datetime.fromtimestamp(path.stat().st_mtime, dt.UTC))
        except OSError:
            continue
    return max(times) if times else None
