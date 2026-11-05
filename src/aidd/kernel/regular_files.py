"""Reading a file of the repository safely: a repository's files are another person's text, so aidd opens only a regular
file inside the repository, never follows a link, and never opens a device, which a read could hang on."""

from __future__ import annotations

import os
import stat
from pathlib import Path

NOT_REGULAR = "not regular"


def regular_file_bytes(root: Path, rel: str, limit: int) -> tuple[bytes | None, str]:
    """At most `limit` + 1 bytes of a regular file inside the repository, or None and why not: "not regular" for a
    symlink, a device, or a file outside the repository, else the OS's error. aidd never follows a link or opens a
    device, which a read could hang on. A caller reads `len(data) > limit` as too large."""
    path = root / rel
    try:
        st = os.lstat(path)
        inside = Path(os.path.realpath(path)).is_relative_to(os.path.realpath(root))
    except OSError as exc:
        return None, str(exc.strerror or exc)
    if not stat.S_ISREG(st.st_mode) or not inside:
        return None, NOT_REGULAR
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        return None, str(exc.strerror or exc)
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):  # swapped since the lstat
            return None, NOT_REGULAR
        try:
            return f.read(limit + 1), ""
        except OSError as exc:
            return None, str(exc.strerror or exc)


def link_on_the_way(root: Path, path: str | Path) -> str:
    """The first symbolic link between `root` and `path`, `path` included, as a path from `root`; "" when there is none. A link
    on the way sends a read or a write to a file somewhere else, and the last part's own lstat never sees it. A path outside
    `root` is not checked. `root` and `path` may each be spelled through a link of their own (`/var` for `/private/var`): the
    root is the shortest front of the path that is the same folder as `root`, and every part after it is checked as written."""
    real_root = os.path.realpath(root)
    parts = Path(os.path.abspath(Path(root) / path)).parts
    for k in range(1, len(parts) + 1):
        front = Path(*parts[:k])
        if os.path.realpath(front) != real_root:
            continue
        here = front
        for part in parts[k:]:
            here = here / part
            if here.is_symlink():
                return here.relative_to(front).as_posix()
        return ""
    return ""


def open_for_write(path: Path, *, text: bool = False):
    """`path` opened and emptied for writing, refusing a link at the path itself: O_NOFOLLOW where the OS has it, and an lstat
    before the open where it has not. A file the repository points elsewhere is never written through."""
    if os.path.islink(path):
        raise OSError(f"{path} is a link, and aidd writes nothing through a link")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags, 0o666)
    return os.fdopen(fd, "w" if text else "wb", encoding="utf-8" if text else None)
