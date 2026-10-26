"""The autopilot store's files in the git directory (config.state_dir): the folder, its lock, and each file written
whole or appended, refusing a symbolic link, a hard link, or another user's file in its place. `lease` keeps the lease,
the journal, and the run events here."""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import stat
import time
from pathlib import Path

from aidd import config

MAX_LINES = 2000  # each journal file keeps its last MAX_LINES lines
LOCK_WAIT_SECONDS = 5.0
LOCK_STALE_S = 30.0
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)  # a FIFO in place of the file never hangs the open


class LeaseError(ValueError):
    """An autopilot command that cannot do what it was asked; the message names the next action."""


def lease_store(root: Path | str) -> Path:
    """The folder in the git directory that holds the lease, the journal, and the run events (config.state_dir)."""
    try:
        return config.state_dir(root)
    except ValueError:
        raise LeaseError("not a git repository: the autopilot lease lives in the git directory") from None


def folder(root: Path | str, *, create: bool = False) -> Path:
    """The store, refused when it, or what it holds, is not what aidd writes: a symbolic link or another kind of file."""
    where = lease_store(root)
    if where.is_symlink():
        raise LeaseError(f"{where} is a symbolic link: aidd writes only a real folder there; remove it")
    if create:
        where.mkdir(mode=0o700, parents=True, exist_ok=True)
    if where.exists() and not where.is_dir():
        raise LeaseError(f"{where} is not a folder: remove it")
    return where


def regular(path: Path) -> bool:
    """True for a regular file, False when absent; any other kind (a link, a folder) is refused."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(st.st_mode):
        raise LeaseError(f"{path} is not a regular file (a symbolic link or a folder): remove it")
    return True


class Lock:
    """An exclusive lock on the store for one read-modify-write. It holds a random token; whoever finds it older than
    LOCK_STALE_S takes it over by renaming it away, so only one waiter wins, and a holder that lost it says so."""

    def __init__(self, folder: Path):
        self.path = folder / ".lock"
        self.token = f"{os.getpid()}-{secrets.token_hex(8)}"

    def __enter__(self) -> Lock:
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            if time.monotonic() > deadline:
                raise LeaseError(f"{self.path} is held by another aidd command; try again")
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | _NOFOLLOW, 0o600)
            except FileExistsError:
                self._maybe_take_over()
                time.sleep(0.02)
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(self.token)
            return self

    def _maybe_take_over(self) -> None:
        try:
            st = os.lstat(self.path)
        except FileNotFoundError:
            return
        if not stat.S_ISREG(st.st_mode):
            raise LeaseError(f"{self.path} is not a regular file (a symbolic link or a folder): remove it")
        if time.time() - st.st_mtime <= LOCK_STALE_S:
            return
        grave = self.path.with_name(f".lock.stale.{self.token}")
        try:
            os.rename(self.path, grave)  # atomic: of two waiters, one renames it
        except FileNotFoundError:
            return
        if os.lstat(grave).st_ino != st.st_ino:  # a fresh lock replaced the stale one meanwhile: give it back
            with contextlib.suppress(FileExistsError, OSError):
                os.link(grave, self.path)
        with contextlib.suppress(OSError):
            os.unlink(grave)

    def check(self) -> None:
        """Before a write: the lock is still this holder's, and fresh."""
        try:
            held = self.path.read_text(encoding="utf-8")
        except OSError:
            held = ""
        if held != self.token:
            raise LeaseError(f"{self.path} was taken over while this command held it; nothing was written, try again")
        with contextlib.suppress(OSError):
            os.utime(self.path)

    def __exit__(self, *exc) -> None:
        with contextlib.suppress(OSError):
            if self.path.read_text(encoding="utf-8") == self.token:
                self.path.unlink()


def replace(lock: Lock, folder: Path, name: str, text: str) -> None:
    """Write the store's file `name` whole, through an exclusive temporary file; a link in its place is refused."""
    regular(folder / name)
    tmp = folder / f".{name}.{secrets.token_hex(8)}"
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | _NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        lock.check()
        os.replace(tmp, folder / name)
    finally:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()


def append(lock: Lock, path: Path, line: dict) -> None:
    """Append one line; past MAX_LINES lines, keep the last MAX_LINES (rewritten through an exclusive temporary file).

    The file opened must be a regular file with one link that this user owns (CWE-59, CWE-62): a hard link to a file
    elsewhere is refused before a byte is written, as is a file that is not UTF-8 (nothing is appended to it)."""
    regular(path)
    lock.check()
    try:
        fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT | _NOFOLLOW | _NONBLOCK, 0o600)
    except OSError as exc:
        raise LeaseError(f"{path} cannot be written ({exc.strerror}): it must be a regular file") from None
    with os.fdopen(fd, "r+b") as fh:
        st = os.fstat(fh.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or (hasattr(os, "geteuid") and st.st_uid != os.geteuid()):
            raise LeaseError(f"{path} is not a file aidd wrote (a hard link, or another user's file): remove it")
        try:
            kept = fh.read().decode("utf-8")
        except UnicodeDecodeError:
            raise LeaseError(f"{path} holds a line that is not UTF-8: remove that line, or the file") from None
        added = json.dumps(line, sort_keys=True) + "\n"
        fh.write(added.encode("utf-8"))
    lines = (kept + added).splitlines(keepends=True)
    if len(lines) > MAX_LINES:
        tmp = path.with_name(f".{path.name}.{secrets.token_hex(8)}")
        fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | _NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("".join(lines[-MAX_LINES:]))
        os.replace(tmp, path)


def lines(path: Path, *, tail: int | None = None) -> list[dict]:
    if not regular(path):
        return []
    with open(path, "rb") as fh:
        if tail is not None:
            size = fh.seek(0, os.SEEK_END)
            fh.seek(max(0, size - tail))
            raw = fh.read().decode("utf-8", errors="replace")
            if size > tail:
                raw = raw.split("\n", 1)[-1]  # the first line may be cut
        else:
            raw = fh.read().decode("utf-8", errors="replace")
    out = []
    for text in raw.splitlines():
        with contextlib.suppress(ValueError):
            item = json.loads(text)
            if isinstance(item, dict):
                out.append(item)
    return out
