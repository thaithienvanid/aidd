"""The roles a lead started that are still running, from their status files: `.aidd/tmp/roles/<role name>.log` in this
checkout, which git ignores. A role appends one line per step, `<HH:MM> <step>: <what runs now>`, and ends with a line
that starts with `DONE`. `aidd status` shows each running role's last line and how long ago the file last changed, so the
lead tells a role at work from a quiet one. The files are plain text a person reads; aidd starts nothing to watch them, and
shows nothing when there are none. A line is a role's text, so it shows on one line, with each secret in it hidden."""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path

from aidd.kernel import documents, regular_files, secret_patterns

ROLES_DIR = ".aidd/tmp/roles"
STATUS_SUFFIX = ".log"
DONE_WORD = "DONE"
# A status file holds one short line per step, so a file past this is no status file: aidd reads none of it.
MAX_STATUS_BYTES = 256 * 1024
# The most status files read, so a folder of many stays fast.
MAX_STATUS_FILES = 200


def _shown(line: str) -> str:
    """A role's status line as every output shows it. A role writes the file, so its line is data that may hold a token or a
    password, as a pasted push URL does: the secret scrub hides each one in the whole line, then one safe line is cut to a
    length, so a secret the cut would split is never half shown."""
    return documents.one_line(secret_patterns.scrubbed(line[: secret_patterns.MAX_SECRET_LINE]), 300)


def running_roles(root: Path, now: float | None = None) -> list[dict]:
    """Each role whose status file's last line does not start with DONE_WORD, by its file's name, with that line and the
    minutes since the file last changed. A link, a folder, or a file aidd refuses is no status file."""
    base = root / ROLES_DIR
    try:
        if not stat.S_ISDIR(os.lstat(base).st_mode):
            return []
        with os.scandir(base) as found:
            names = sorted(e.name for e in found if e.name.endswith(STATUS_SUFFIX) and e.is_file(follow_symlinks=False))
    except OSError:
        return []
    now = time.time() if now is None else now
    out = []
    for name in names[:MAX_STATUS_FILES]:
        rel = f"{ROLES_DIR}/{name}"
        text, _ = regular_files.named_text(root, rel, MAX_STATUS_BYTES)
        lines = [line for line in (text or "").splitlines() if line.strip()]
        if text is None or len(text.encode("utf-8")) > MAX_STATUS_BYTES or not lines or lines[-1].lstrip().startswith(DONE_WORD):
            continue
        try:
            changed = os.lstat(root / rel).st_mtime
        except OSError:
            continue
        out.append(
            {
                "name": documents.one_line(name.removesuffix(STATUS_SUFFIX), 100),
                "last_line": _shown(lines[-1]),
                "quiet_minutes": max(0, int((now - changed) // 60)),
            }
        )
    return out


def running_roles_text(roles: list[dict]) -> str:
    """The running roles as `aidd status` prints them after the open work, one line each, or "" when none runs."""
    if not roles:
        return ""
    rows = "".join(f"  {r['name']}: {r['last_line']} ({r['quiet_minutes']} minutes ago)\n" for r in roles)
    return f"running roles, from their status files in {ROLES_DIR}/:\n{rows}"
