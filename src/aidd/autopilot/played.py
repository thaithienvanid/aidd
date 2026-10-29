"""The role a main session plays in its own session (role placement `lead`), as the session declared it with
`aidd context <ID> --role <role> --play --session <id>`.

The guard reads it to hold that session's edits to the role's write area as well as to the session's own rules, so a
declaration only ever narrows what the session may write: a wrong or forged one can only restrict. One file per
session, in the store beside the autopilot lease. A declaration ends with `aidd context --stop-playing --session <id>`,
with another `--play`, or after PLAY_HOURS.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import stat
from pathlib import Path

from aidd import workitems
from aidd.autopilot import store
from aidd.autopilot.lease import SESSION_ID
from aidd.autopilot.store import LeaseError
from aidd.kernel import timestamps

PLAY_HOURS = 12
MAX_BYTES = 4096  # a record is one short line


def _name(session_id: str) -> str:
    if not isinstance(session_id, str) or not SESSION_ID.match(session_id):
        raise LeaseError(f"session {session_id!r} is not a session id: pass the one the session hook named, `--session <id>`")
    return f"played-{session_id}.json"


def declare_played(root: Path | str, session_id: str, role: str, now: dt.datetime | None = None) -> None:
    """Record that `session_id` plays `role` from now on."""
    if role not in workitems.role_ids():
        raise LeaseError(f"no role {role!r}; `aidd owners` lists every role")
    name = _name(session_id)
    folder = store.folder(root, create=True)
    at = (now or dt.datetime.now(dt.UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with store.Lock(folder) as lock:
        store.replace(lock, folder, name, json.dumps({"role": role, "at": at}) + "\n")


def stop_playing(root: Path | str, session_id: str) -> bool:
    """End `session_id`'s played role; False when it played none."""
    name = _name(session_id)
    folder = store.folder(root)
    path = folder / name
    if not path.exists():
        return False
    store.regular(path)
    with store.Lock(folder):
        path.unlink(missing_ok=True)
    return True


def played_role(root: Path | str, session_id: object, now: dt.datetime | None = None) -> str | None:
    """The role `session_id` plays now, or None. A record aidd cannot read raises LeaseError, so the guard denies the
    edit (fail closed) and names the command that ends it; a stale one plays nothing."""
    if not isinstance(session_id, str) or not SESSION_ID.match(session_id):
        return None
    ends = f"`aidd context --stop-playing --session {session_id}` ends it"
    try:
        path = store.folder(root) / f"played-{session_id}.json"
        text = _read(path)
        if text is None:
            return None
        data = json.loads(text)
        role, at = (data.get("role"), data.get("at")) if isinstance(data, dict) else (None, None)
        if not isinstance(role, str) or not isinstance(at, str) or (when := timestamps.parse_time(at)) is None:
            raise ValueError("it holds no role and time")
    except LeaseError:
        raise
    except PermissionError as exc:
        where = store.lease_store(root)
        raise LeaseError(f"aidd's store {where} cannot be read ({exc.strerror}): a person restores its permissions, `chmod 700 {where}`") from None
    except (OSError, ValueError) as exc:
        raise LeaseError(f"this session's played role cannot be read ({exc}); {ends}") from None
    if role not in workitems.role_ids():
        raise LeaseError(f"{path} names no role aidd has ({role!r}); {ends}")
    if (now or dt.datetime.now(dt.UTC)) - when > dt.timedelta(hours=PLAY_HOURS):
        return None
    return role


def _read(path: Path) -> str | None:
    """The record's text, or None when there is none. Only a regular file with one link is read, opened without
    following a link or waiting on a FIFO, and at most MAX_BYTES of it; any other kind raises."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "rb") as fh:
        st = os.fstat(fh.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            raise LeaseError(f"{path} is not a file aidd wrote (a link, a FIFO, or a folder): remove it")
        return fh.read(MAX_BYTES).decode("utf-8")
