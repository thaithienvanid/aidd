"""`AIDD_HOOK_CAPTURE=<file>`: a copy of each raw hook event, so a harness's dialect can be checked against a real session.

The harness starts the hook with the variable set, from its hook settings or a live check's scratch setup; an agent's
shell cannot set a hook's environment. The hook appends the event to that file before the dialect reads it, then
decides as it always does. It writes only that local file: no network call. An event can hold a prompt or a file's
content, so the file is the person's: mode 0600, never through a symbolic link, and capped, so a long session never
fills the disk.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import stat
import sys
from pathlib import Path

ENV = "AIDD_HOOK_CAPTURE"
MAX_BYTES = 8 * 1024 * 1024  # past this size the file takes no more events


def keep(hook: str, raw: str) -> None:
    """When AIDD_HOOK_CAPTURE names a file, append the raw event `hook` read there. Each hook calls it right after it
    reads the event, inside its own deadline and error handling, so the copy can never change or delay its answer past
    them. Any failure only skips the copy, with a line on stderr."""
    target = os.environ.get(ENV, "").strip()
    if not target:
        return
    try:
        _append(Path(os.path.expanduser(target)), hook, raw)
    except Exception as exc:  # noqa: BLE001  # the copy is a courtesy: the hook decides as usual
        print(f"aidd hook {hook}: {ENV} not written ({exc}); the hook decides as usual", file=sys.stderr)


def _append(path: Path, hook: str, raw: str) -> None:
    """One JSON line: the hook, the time, and the event as it came (parsed when it is JSON, else the text). The file is
    this user's alone: a new one is 0600, an existing one must be theirs and is set back to 0600, and a link, a pipe,
    or a device is refused without waiting on it (O_NOFOLLOW, O_NONBLOCK)."""
    if not path.is_absolute():
        raise ValueError("it must be an absolute path")
    try:
        event: object = json.loads(raw)
    except ValueError:
        event = raw
    line = json.dumps({"hook": hook, "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "event": event}) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("it is not a regular file")
        if hasattr(os, "getuid") and info.st_uid != os.getuid():
            raise ValueError("another user owns it")
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        if info.st_size + len(line.encode()) > MAX_BYTES:
            raise ValueError(f"it holds {MAX_BYTES // (1024 * 1024)} MiB already")
        os.write(fd, line.encode())
    finally:
        os.close(fd)
