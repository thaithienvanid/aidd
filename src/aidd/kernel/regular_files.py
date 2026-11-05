"""Reading a file of the repository safely: a repository's files are another person's text, so aidd opens only a regular
file inside the repository, never follows a link, and never opens a device, which a read could hang on."""

from __future__ import annotations

import contextlib
import contextvars
import io
import os
import posixpath
import stat
from collections.abc import Iterator
from pathlib import Path

NOT_REGULAR = "not regular"

# The writes a plan holds in place of making them (`holding_writes`), by the path from the repository's top.
_held_writes: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar("held_writes", default=None)
# The files a plan would delete (`hold_removal`), by the same path: they read as missing for the rest of the plan.
_held_removals: contextvars.ContextVar[set[str] | None] = contextvars.ContextVar("held_removals", default=None)


@contextlib.contextmanager
def holding_writes() -> Iterator[dict[str, str]]:
    """Run the code inside as it would run, with every write to a repository file held in the dict this yields, by its path
    from the repository's top, and written nowhere. A read of a held file in the same run gives the held text, so a later
    step sees what an earlier one wrote. A refusal (a link on the way, a device) is the real one. This is how a dry run
    plans with the code that applies."""
    held: dict[str, str] = {}
    token, gone = _held_writes.set(held), _held_removals.set(set())
    try:
        yield held
    finally:
        _held_writes.reset(token)
        _held_removals.reset(gone)


# The files a step of a dry run would have written already, by the same path: reads see them, and nothing is held back from a write.
_overlay: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar("overlay", default=None)


@contextlib.contextmanager
def reading_as(texts: dict[str, str]) -> Iterator[None]:
    """Run the code inside with every read of a repository file in `texts`, by its path from the repository's top, giving
    that text. A dry run reads the files an earlier step would have changed this way, and its other steps still write
    nothing and run as they run for real, unlike `holding_writes`, which holds every write."""
    token = _overlay.set(dict(texts))
    try:
        yield
    finally:
        _overlay.reset(token)


def writes_held() -> bool:
    """Whether the code is running inside `holding_writes`: a step that writes by another way than this module, such as a
    folder copy or a link, says what it would do and does nothing."""
    return _held_writes.get() is not None


def _held_key(root: Path, path: str | Path) -> str:
    """The key of the file at `path` in the held writes: its path from `root`, in forward slashes."""
    return posixpath.normpath(Path(os.path.relpath(os.path.abspath(Path(root) / path), os.path.abspath(root))).as_posix())


def hold_removal(root: Path, path: str | Path) -> bool:
    """Inside a plan, note that the file at `path` would be deleted, and leave it where it is; whether it was a file. A file
    an earlier step of the plan wrote is dropped from the held writes."""
    key = _held_key(root, path)
    there = is_file_or_held(root, path)
    (_held_writes.get() or {}).pop(key, None)
    if (gone := _held_removals.get()) is not None:
        gone.add(key)
    return there


def held_removals() -> list[str]:
    """The files the plan running now would delete, by path from the repository's top."""
    return sorted(_held_removals.get() or ())


def held_text(root: Path, rel: str) -> str | None:
    """The text a held write left at `rel` in `root`, else None, also outside `holding_writes`."""
    key = posixpath.normpath(rel.replace("\\", "/"))
    if is_outside(rel):
        return None
    for held in (_held_writes.get(), _overlay.get()):
        if held is not None and key in held:
            return held[key]
    return None


def _removed(root: Path, rel: str) -> bool:
    return _held_writes.get() is not None and not is_outside(rel) and posixpath.normpath(rel.replace("\\", "/")) in (_held_removals.get() or ())


def hold_write(root: Path, path: str | Path, text: str) -> None:
    """Hold `text` as the file at `path` in `root`, for a step that writes by another way than this module, such as a folder
    copy, so the plan lists it. Nothing is held outside `holding_writes`."""
    if (held := _held_writes.get()) is not None:
        held[_held_key(root, path)] = text


def is_file_or_held(root: Path, path: str | Path) -> bool:
    """Whether a regular file is at `path` in `root`, or a held write put one there."""
    held = _held_writes.get()
    if (held is not None and _held_key(root, path) in held) or _held_key(root, path) in (_overlay.get() or {}):
        return True
    return (Path(root) / path).is_file() and (held is None or _held_key(root, path) not in (_held_removals.get() or ()))


def regular_file_bytes(root: Path, rel: str, limit: int) -> tuple[bytes | None, str]:
    """At most `limit` + 1 bytes of a regular file inside the repository, or None and why not: "not regular" for a
    symlink, a device, or a file outside the repository, else the OS's error. aidd never follows a link or opens a
    device, which a read could hang on. A caller reads `len(data) > limit` as too large."""
    if problem := relative_root_problem(root):
        return None, problem
    if (text := held_text(root, rel)) is not None:
        return text.encode("utf-8")[: limit + 1], ""
    if _removed(root, rel):
        return None, "No such file or directory"
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


# Why `named_file_bytes` reads nothing, besides the OS's own error: a link, an absolute path or one through `..`, and a
# file past the limit; and, from `named_text`, a missing file. NOT_REGULAR then means a device, a pipe, or another file
# that is not regular.
LINK, OUTSIDE, TOO_LARGE, MISSING = "a link", "outside", "too large", "missing"


def is_outside(rel: str) -> bool:
    """Whether a path a repository names leaves the repository by its text alone: empty, absolute, a Windows drive, or
    through `..`. It is judged before anything is read or even stat'ed."""
    parts = rel.replace("\\", "/").split("/")
    return not rel or rel.startswith(("/", "\\")) or os.path.isabs(rel) or (len(rel) > 1 and rel[1] == ":") or ".." in parts


def named_file_bytes(root: Path, rel: str, limit: int) -> tuple[bytes | None, str]:
    """At most `limit` bytes of the regular file a repository names at `rel`, or None and why not: OUTSIDE for a path
    `is_outside` refuses, before any read; LINK for a link at the path or on the way; NOT_REGULAR for a device, a pipe,
    or a file outside the repository; TOO_LARGE past `limit`; else the OS's error."""
    if is_outside(rel):
        return None, OUTSIDE
    raw, why = regular_file_bytes(root, rel, limit)
    if why == NOT_REGULAR and (os.path.islink(root / rel) or link_on_the_way(root, rel)):
        return None, LINK
    if raw is not None and len(raw) > limit:
        return None, TOO_LARGE
    return raw, why


# The most a repository file aidd reads whole may hold, such as an agent's settings file: a file past it is refused.
MAX_REPOSITORY_FILE = 1024 * 1024


def named_text(root: Path, rel: str, limit: int = MAX_REPOSITORY_FILE) -> tuple[str | None, str]:
    """The text of the regular file a repository holds at `rel` (`named_file_bytes`), or None and why not. This is the
    one way aidd reads a repository's file whole: a missing file says MISSING, so a caller can tell it from one aidd
    refuses. Bytes that are not UTF-8 read as U+FFFD."""
    if problem := relative_root_problem(root):
        return None, problem
    if (held := held_text(root, rel)) is not None:
        return held, ""
    if _removed(root, rel):
        return None, MISSING
    if not is_outside(rel) and link_on_the_way(Path(root), rel):
        return None, LINK  # never MISSING behind a link: a write there would land somewhere else
    if not is_outside(rel) and not os.path.lexists(Path(root) / rel):
        return None, MISSING
    raw, why = named_file_bytes(Path(root), rel, limit)
    return (raw.decode("utf-8", errors="replace") if raw is not None else None), why


def repository_text(root: Path, rel: str, limit: int = MAX_REPOSITORY_FILE) -> str | None:
    """`named_text`'s text alone: None when the file is missing or aidd refuses it."""
    return named_text(root, rel, limit)[0]


def text_at(root: Path, path: Path, limit: int = MAX_REPOSITORY_FILE) -> str | None:
    """The text of a file aidd reads that may lie in the repository `root` or outside it, such as a harness's settings in
    the person's home: one inside the repository through `named_text`, one outside as it is, since it is the person's own
    and a dotfile there may be a link of theirs. None when there is none to read."""
    if Path(path).is_relative_to(root):
        return repository_text(root, Path(path).relative_to(root).as_posix(), limit)
    return own_text(Path(path), limit)


def own_text(path: Path, limit: int = MAX_REPOSITORY_FILE) -> str | None:
    """The text of a file of the person's own, outside any repository, such as `~/.claude/settings.json`. A link there is
    theirs, such as a dotfiles link, so it is followed. A device or a pipe is still never opened, and a file past `limit`
    is refused. None when there is none to read. Bytes that are not UTF-8 read as U+FFFD."""
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    try:
        if not stat.S_ISREG(os.stat(path).st_mode):
            return None
        with os.fdopen(os.open(path, flags), "rb") as f:
            raw = f.read(limit + 1) if stat.S_ISREG(os.fstat(f.fileno()).st_mode) else None  # swapped since the stat
    except OSError:
        return None
    return raw.decode("utf-8", errors="replace") if raw is not None and len(raw) <= limit else None


def file_bytes(root: Path, path: Path, limit: int) -> tuple[bytes | None, str]:
    """At most `limit` bytes of the regular file at `path`, read as `named_file_bytes` reads it from the repository
    `root`, or None and why not: never through a link at the path or on the way from `root`, never from a device or a
    pipe, and never past `limit`. A path outside `root` is OUTSIDE."""
    return named_file_bytes(Path(root), relative(root, path), limit)


def relative(root: Path, path: Path) -> str:
    """`path` as a path from `root`, spelled as written: through `..` when it lies outside, which `is_outside` refuses."""
    try:
        return Path(os.path.relpath(os.path.abspath(path), os.path.abspath(root))).as_posix()
    except ValueError:  # another drive
        return str(path)


def file_head(root: Path, path: Path, limit: int) -> bytes | None:
    """The first `limit` bytes of the regular file at `path`, inside the repository `root`, never through a link at the
    path or on the way and never from a device or a pipe; None when aidd refuses it. A file past `limit` is read in
    part, never refused, for a reader that needs only its head, such as a manifest's test command."""
    rel = relative(root, path)
    if relative_root_problem(root) or is_outside(rel) or link_on_the_way(Path(root), rel):
        return None
    raw, _ = regular_file_bytes(Path(root), rel, limit)
    return raw[:limit] if raw is not None else None


def file_text(root: Path, path: Path, limit: int) -> str | None:
    """`file_bytes`'s text, or None when it reads nothing. Bytes that are not UTF-8 read as U+FFFD."""
    raw, _ = file_bytes(root, path, limit)
    return raw.decode("utf-8", errors="replace") if raw is not None else None


def working_root(path: Path) -> Path:
    """The repository root a command reads or writes `path` from when it has none at hand: the working folder, which is
    the repository's top where a command runs, when `path` lies in it; else the path's own folder. That fallback checks
    for a link only at the file itself, and it is enough: a path outside the working folder is one the person typed,
    such as `aidd validate ~/notes/SPEC-1.md`, never one a repository names."""
    spelled = Path(os.path.abspath(path))
    return Path(".") if spelled.is_relative_to(os.getcwd()) else spelled.parent


def relative_root_problem(root: Path) -> str:
    """Why aidd reads and writes nothing under `root`, or "": a relative root other than `.` leaves it unsaid whether a path
    already holds the root, so a caller makes the root absolute first (`Path(root).absolute()`)."""
    if Path(root).is_absolute() or Path(root) == Path("."):
        return ""
    return f"the folder {Path(root).as_posix()} is a relative path, and aidd reads and writes nothing under one: pass its absolute path (Path(root).absolute()), then run aidd again"


def from_root(root: Path, path: str | Path) -> tuple[Path, tuple[str, ...]] | None:
    """`path` as a full path, and its parts after `root`, as written, or None when it does not lie inside `root`. `path` is
    either relative to `root` or absolute and under it: an absolute path is never joined onto `root` again. `root` is
    read as it was chosen, so a `..` in it is no part of the path after it. An absolute `path` may spell `root` as
    given, normalized, through its links, or through a link of its own (`/var` for `/private/var`): then the root is the
    shortest front of the path that is the same folder as `root`. The check and the open both use the path returned."""
    top, given = Path(root), Path(path)
    if not given.is_absolute():
        return top.absolute() / given, given.parts
    for base in dict.fromkeys((top.absolute(), Path(os.path.abspath(top)), Path(os.path.realpath(top)))):
        if given.parts[: len(base.parts)] == base.parts:
            return given, given.parts[len(base.parts) :]
    real_root = os.path.realpath(top)
    for k in range(1, len(given.parts)):
        if os.path.realpath(Path(*given.parts[:k])) == real_root:
            return given, given.parts[k:]
    return None


def link_on_the_way(root: Path, path: str | Path) -> str:
    """The first symbolic link between `root` and `path`, `path` included, as a path from `root`; "" when there is none. A link
    on the way sends a read or a write to a file somewhere else, and the last part's own lstat never sees it. A path that
    lies outside `root` comes back whole, as one to refuse, so this never passes a path it did not check. A `..` part after
    `root` comes back whole too: after a link, `..` climbs out of the link's target, which a folded path would never show."""
    if problem := relative_root_problem(root):
        return problem
    placed = from_root(root, path)
    if placed is None:
        return f"{Path(path).as_posix()} (not inside {root})"
    full, tail = placed
    if ".." in tail:
        return Path(*tail).as_posix()
    front = Path(*full.parts[: len(full.parts) - len(tail)])
    here = front
    for part in tail:
        here = here / part
        if here.is_symlink():
            return here.relative_to(front).as_posix()
    return ""


class WriteRefused(OSError):
    """aidd writes nothing at a path: a link at its name or on the way to it, or a file there that is not regular. The
    message names the link or the file, and the next step."""


def write_refusal(root: Path, path: str | Path) -> str:
    """Why aidd writes nothing at `path` in the folder `root`, or "" when it may: a path outside `root`; one with a `..`
    after `root`; a link at the path or on the way to it, which would send the write somewhere else; or a device, a pipe,
    a folder, or a hard link (a file with another name too) at the path. `path` is relative to `root`, or absolute and
    under it. The reason names the path, and the next step."""
    if problem := relative_root_problem(root):
        return problem
    placed = from_root(root, path)
    if placed is None:
        return f"{Path(path).as_posix()} lies outside {root}, and aidd writes nothing there: name a file inside it, then run aidd again"
    full, tail = placed
    if ".." in tail:
        folded = Path(os.path.abspath(full))
        if not folded.is_relative_to(os.path.abspath(root)) and not folded.is_relative_to(os.path.realpath(root)):
            return f"{Path(*tail).as_posix()} lies outside {root}, and aidd writes nothing there: name a file inside it, then run aidd again"
        return f"{Path(*tail).as_posix()} goes through `..`, and aidd writes nothing through it: name the file by its path inside {root}, then run aidd again"
    if link := link_on_the_way(root, full):
        return f"{link} is a link, and aidd writes nothing through a link: remove the link, then run aidd again"
    try:
        st = os.lstat(full)
    except OSError:
        return ""
    return _not_writable(Path(*tail).as_posix(), st)


def _placed(root: Path, path: str | Path) -> Path:
    """The full path `path` stands for in `root`, once `write_refusal` allows a write there; else WriteRefused."""
    if why := write_refusal(root, path):
        raise WriteRefused(why)
    placed = from_root(root, path)
    assert placed is not None
    return placed[0]


def _not_writable(shown: str, st: os.stat_result) -> str:
    """Why a file aidd found at a path is not one it writes: one that is not regular, or a hard link, whose other name may
    lie anywhere on the same disk; "" for a regular file with one name."""
    if not stat.S_ISREG(st.st_mode):
        return f"{shown} is not a regular file, and aidd writes nothing into it: replace it with the file, then run aidd again"
    if st.st_nlink > 1:
        return f"{shown} is a hard link, another name of a file that may lie elsewhere, and aidd writes nothing into it: replace it with a copy, then run aidd again"
    return ""


# How `open_for_write` opens a file: emptied once it is checked, added to at its end, or only when nothing is there yet.
WRITE_FLAGS = {"replace": 0, "append": os.O_APPEND, "new": os.O_EXCL}


def open_for_write(path: Path, *, text: bool = False, root: Path | None = None, way: str = "replace", mode: int = 0o600):
    """`path` opened for writing the `way` WRITE_FLAGS names, refusing a link at the path itself: O_NOFOLLOW where the OS
    has it, and an lstat before the open where it has not. A "new" open fails with FileExistsError when a file is there.
    With `root`, a path outside it, a link anywhere between it and `path`, and a device or a pipe at the path, are refused
    too (`write_refusal`). The opened file must be a regular file with one name, never a hard link, and only then is it
    emptied. A refusal is WriteRefused, so a file the repository points elsewhere is never written through. A file it
    creates gets `mode` under the person's umask: by default the owner's alone (0o600), so no file it writes, such as a
    test's log, is readable by others. Git records no read bits, so a commit and a teammate's checkout read it as usual.
    A file that exists keeps its own mode."""
    if root is not None:
        path = _placed(root, path)
        if (held := _held_writes.get()) is not None:
            return _HeldFile(held, root, path, way)
    if os.path.islink(path):
        raise WriteRefused(f"{path} is a link, and aidd writes nothing through a link: remove the link, then run aidd again")
    flags = os.O_WRONLY | os.O_CREAT | WRITE_FLAGS[way] | getattr(os, "O_BINARY", 0)
    if mode == REPOSITORY_FILE_MODE:
        mode = mode_like_folder(Path(path).parent)
    fd = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0), mode)
    if why := _not_writable(str(path), os.fstat(fd)):  # swapped since the check; O_NONBLOCK kept a pipe's open from hanging
        os.close(fd)
        raise WriteRefused(why)
    if way == "replace":
        os.ftruncate(fd, 0)
    return os.fdopen(fd, ("a" if way == "append" else "w") + ("" if text else "b"), encoding="utf-8" if text else None)


def _hold(held: dict[str, str], root: Path, path: Path, text: str, way: str) -> None:
    """Keep `text` as the file at `path` would hold it after a write the `way` WRITE_FLAGS names."""
    key = _held_key(root, path)
    if (gone := _held_removals.get()) is not None:
        gone.discard(key)
    before = held.get(key)
    if before is None and way != "replace":
        before = own_text(path)  # what is on disk now; an append adds to it
    if way == "new" and (before is not None or os.path.lexists(path)):
        raise FileExistsError(f"{path} exists")
    held[key] = (before or "") + text if way == "append" else text


class _HeldFile(io.StringIO):
    """A file object whose text goes to the held writes when it closes."""

    def __init__(self, held: dict[str, str], root: Path, path: Path, way: str) -> None:
        super().__init__()
        self.held, self.root, self.path, self.way, self.done = held, root, path, way, False

    def close(self) -> None:
        if not self.done:
            self.done = True
            _hold(self.held, self.root, self.path, self.getvalue(), self.way)
        super().close()


# A repository file aidd creates is never more open than the folder it goes into: the owner reads and writes it, the
# group gets what the folder gives the group (read, and write on a team's shared folder), others may read it only when
# they may read the folder, and nobody else ever writes it. The person's umask narrows it further, as for any file.
REPOSITORY_FILE_MODE = -1  # "follow the folder": open_for_write works the mode out when it creates the file


def mode_like_folder(folder: Path) -> int:
    """The mode a new file in `folder` is created with: 0o600, plus the folder's own group read and write and its
    others' read bits. Others never get write, and nothing is executable."""
    return 0o600 | (stat.S_IMODE(os.stat(folder).st_mode) & 0o064)


def write_safely(root: Path, path: str | Path, data: str | bytes, *, way: str = "replace", mode: int = REPOSITORY_FILE_MODE) -> None:
    """Write `data` to the file at `path` in the folder `root` the `way` WRITE_FLAGS names, making its folders, never
    through a link: a path outside `root`, a link at the path or on the way to it, or a device, a pipe, or a hard link
    there, raises WriteRefused, which names it and the next step, before any folder is made. Text is written as UTF-8,
    bytes as they are. This is the one way aidd writes a file in a repository or in its git folder."""
    full = _placed(root, path)
    if (held := _held_writes.get()) is not None:
        _hold(held, root, full, data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data, way)
        return
    full.parent.mkdir(parents=True, exist_ok=True)
    with open_for_write(full, text=isinstance(data, str), root=root, way=way, mode=mode) as f:
        f.write(data)


def write_text_safely(root: Path, path: str | Path, text: str, *, append: bool = False) -> None:
    """`write_safely` for a repository's text file, replaced, or added to at its end with `append`."""
    write_safely(root, path, text, way="append" if append else "replace")
