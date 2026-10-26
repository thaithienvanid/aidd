"""The watched state: what the always-on rules stand on, which outside_changes.py keeps at a person's decision, read from disk.

It holds the guard's wiring files by content, the branch HEAD names, the decision records (and the ref aidd kept them on before 1.0), the base branch and each
remote's copy of it, every git config key of the repository that names a program or decides signing (ref_writes' registry,
by a hash of its values), the git hooks it runs, and this user's launcher with the program it runs. Files, HEAD, the refs, and the
hooks are read directly, as git reads them; the config through git, only when the files that set it changed. Whatever
cannot be read raises OSError, ValueError, or git.GitError, and the check applies its fail-closed rule.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
from pathlib import Path
from typing import NamedTuple

from aidd import workitems
from aidd.guard import ref_writes
from aidd.kernel import git

MAX_HOOKS = 64
ABSENT = "absent"
BASE_NAMES = ("main", "master", "trunk")


class Place(NamedTuple):
    """A worktree's top, its own git folder, and the folder every worktree of the repository shares."""

    top: str
    git_dir: Path
    common: Path


def place(top: str) -> Place:
    """Where `top`'s git folders are: read from its `.git`, as git finds them, and asked of git when that fails."""
    dot = Path(top) / ".git"
    with contextlib.suppress(OSError, ValueError):
        if dot.is_dir():
            git_dir = dot
        else:
            line = dot.read_text(encoding="utf-8").strip()
            if not line.startswith("gitdir:"):
                raise ValueError(".git names no git folder")
            git_dir = Path(top) / line.removeprefix("gitdir:").strip()
        common_file = git_dir / "commondir"
        common = git_dir / common_file.read_text(encoding="utf-8").strip() if common_file.is_file() else git_dir
        if (git_dir / "HEAD").is_file():
            return Place(top, git_dir.resolve(), common.resolve())
    found = git.run(["rev-parse", "--absolute-git-dir", "--git-common-dir"], top).splitlines()
    common = Path(found[1]) if Path(found[1]).is_absolute() else Path(top) / found[1]
    return Place(top, Path(found[0]).resolve(), common.resolve())


def _content(path: Path) -> str:
    """A file's value in the watched state: its SHA-256 (after `link:` for a symbolic link), or ABSENT. OSError when unreadable."""
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                digest.update(chunk)
    except (FileNotFoundError, NotADirectoryError):
        return ABSENT
    except IsADirectoryError:
        return "folder"
    return ("link:" if path.is_symlink() else "") + digest.hexdigest()


def watched_files() -> tuple[str, ...]:
    """The files of a worktree the watched state holds by content: the guard's wiring (the config counts by its control keys,
    outside_changes.changes)."""
    from aidd.guard import edit_check

    return tuple(edit_check.GUARD_WIRING)


def _ref_values(where: Place, names: list[str]) -> dict[str, str]:
    """Each ref's value (a commit, `ref: <target>` for a symbolic one, or ABSENT), read from its file or packed-refs;
    from git where refs live elsewhere (reftable)."""
    if (where.common / "reftable").exists():
        listed = git.run(["for-each-ref", "--format=%(refname)%00%(objectname)", *names], where.top).splitlines()
        found = dict(line.split("\0", 1) for line in listed if "\0" in line)
        return {n: found.get(n, ABSENT) for n in names}
    packed: dict[str, str] | None = None
    out = {}
    for name in names:
        try:
            text: str | None = (where.common / name).read_text(encoding="utf-8").strip()
        except (FileNotFoundError, NotADirectoryError, IsADirectoryError):
            text = None
        if text is None:
            packed = _packed(where.common) if packed is None else packed
            out[name] = packed.get(name, ABSENT)
        elif text.startswith("ref:") or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", text):
            out[name] = text
        else:
            raise ValueError(f"{name} holds no value git writes")
    return out


def _packed(common: Path) -> dict[str, str]:
    try:
        lines = (common / "packed-refs").read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}
    return {name: sha for sha, _, name in (line.partition(" ") for line in lines) if name and not sha.startswith(("#", "^"))}


def _base_names(where: Place) -> list[str]:
    """The base branch's refs: main, master, trunk, and the branch the remote's HEAD names, and each remote's copy of
    them (a remote-tracking ref a program writes could make a move look fetched)."""
    remote = _ref_values(where, ["refs/remotes/origin/HEAD"])["refs/remotes/origin/HEAD"]
    named = remote.removeprefix("ref:").strip().removeprefix("refs/remotes/origin/") if remote.startswith("ref:") else ""
    names = list(dict.fromkeys([*BASE_NAMES, *([named] if named and named != "HEAD" else [])]))
    return [f"refs/heads/{n}" for n in names] + [f"refs/remotes/{r}/{n}" for r in _remotes(where) for n in names]


def _remotes(where: Place) -> list[str]:
    """The remotes this repository keeps remote-tracking refs for, from their folders and packed-refs."""
    found = set()
    with contextlib.suppress(OSError):
        found |= {p.name for p in (where.common / "refs" / "remotes").iterdir() if p.is_dir()}
    found |= {name.split("/")[2] for name in _packed(where.common) if name.startswith("refs/remotes/") and name.count("/") >= 3}
    return sorted(found)


def _config_keys(where: Place, cache: dict | None) -> tuple[dict[str, str], str, dict]:
    """Every key of the repository's own config that names a program (local and worktree scope, with what they include),
    each by a hash of its values so no secret is kept; the hooks folder it names (core.hooksPath); and the cache that skips git while
    the files that set them read the same."""
    if cache and isinstance(cache.get("files"), dict) and isinstance(cache.get("keys"), dict):
        if all(_content(Path(p)) == v for p, v in cache["files"].items()):
            return cache["keys"], str(cache.get("hooks") or ""), cache
    raw = git.run(["config", "--list", "--null", "--show-scope", "--show-origin"], where.top)
    tokens = raw.split("\0")
    values: dict[str, list[str]] = {}
    origins = {str(where.common / "config"), str(where.git_dir / "config.worktree")}
    for scope, origin, entry in zip(tokens[::3], tokens[1::3], tokens[2::3], strict=False):
        if scope not in ("local", "worktree"):
            continue
        if origin.startswith("file:"):
            origins.add(str(Path(where.top) / origin.removeprefix("file:")))
        key, _, value = entry.partition("\n")
        if not (ref_writes._program_key(key, renames=False) or ref_writes._signing_key(key)):
            continue  # a key that names no program git runs, and decides no signature, is no rule's to hold
        values.setdefault(f"config:{key.lower()}", []).append(value)
    keys = {k: hashlib.sha256("\0".join(v).encode("utf-8", "replace")).hexdigest()[:16] for k, v in values.items()}
    hooks = (values.get("config:core.hookspath") or [""])[-1]
    return keys, hooks, {"files": {p: _content(Path(p)) for p in sorted(origins)}, "keys": keys, "hooks": hooks}


def _hooks(where: Place, chosen: str) -> dict[str, str]:
    """The git hooks the repository runs: each file in its hooks folder (`chosen`, core.hooksPath, else hooks/),
    samples aside."""
    folder = Path(chosen).expanduser() if chosen else where.common / "hooks"
    folder = folder if folder.is_absolute() else Path(where.top) / folder
    try:
        names = sorted(os.listdir(folder))
    except (FileNotFoundError, NotADirectoryError):
        return {}
    out: dict[str, str] = {}
    for name in names:
        if name.endswith(".sample") or not (folder / name).is_file():
            continue
        if len(out) == MAX_HOOKS:
            out["hook:..."] = "more hooks than the guard reads"
            break
        out[f"hook:{name}"] = _content(folder / name)
    return out


def watched_state(where: Place, cache: dict | None = None) -> tuple[dict[str, str], dict]:
    """The watched state (the module docstring says what it holds), and the config cache for the next one. OSError,
    ValueError, or git.GitError when a part of it cannot be read."""
    out = {f"file:{rel}": _content(Path(where.top) / rel) for rel in watched_files()}
    head = (where.git_dir / "HEAD").read_text(encoding="utf-8", errors="replace").strip()
    out["head"] = head.removeprefix("ref:").strip() if head.startswith("ref:") else "detached"
    out |= {f"ref:{name}": value for name, value in _ref_values(where, [workitems.DECISIONS_REF, *_base_names(where)]).items()}
    keys, hooks, cache = _config_keys(where, cache)
    launcher, cache["target"] = launcher_items(cache.get("target"))
    out |= keys | _hooks(where, hooks) | launcher
    return {k: v for k, v in out.items() if v != ABSENT or k.startswith("file:")}, cache


def launcher_items(cached: object = None) -> tuple[dict[str, str], dict]:
    """This user's launcher, which every repository's hooks start (setup.user_launcher), and the program it runs, each
    by content. The program's hash is kept with its size, times, and inode (`cached`), and taken again when any of them
    moved: a write always moves its change time, which no program can set back."""
    import shlex

    from aidd import setup

    path = setup.user_launcher()
    out = {f"launcher:{path}": _content(path)}
    kept: dict = {}
    with contextlib.suppress(OSError, UnicodeDecodeError, ValueError, StopIteration):
        line = next(x for x in path.read_text(encoding="utf-8").splitlines() if x.startswith("exec "))
        program = shlex.split(line.removeprefix("exec "))[0]
        try:
            st = os.stat(program)
        except FileNotFoundError:
            out[f"launcher-target:{program}"] = ABSENT
            return out, kept
        stamp = [program, st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_ino]
        same = isinstance(cached, dict) and cached.get("stamp") == stamp and isinstance(cached.get("hash"), str)
        digest = cached["hash"] if same else _content(Path(program))  # type: ignore[index]
        out[f"launcher-target:{program}"], kept = digest, {"stamp": stamp, "hash": digest}
    return out, kept
