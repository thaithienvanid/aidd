"""The config files of Codex and OpenCode, read as `aidd doctor --autopilot` reads them: bounded, never through a link
inside the repository, and never a device or a pipe. And whether Codex's sandbox lets a run write the git directory.
"""

from __future__ import annotations

import json
import os
import shlex
import stat
import tomllib
from pathlib import Path

from aidd.kernel import git

# A harness's config is a page or two; aidd reads no more than this of one.
HARNESS_CONFIG_MAX_BYTES = 1024 * 1024


def codex_home() -> Path:
    return Path(os.environ["CODEX_HOME"]).expanduser() if os.environ.get("CODEX_HOME") else Path.home() / ".codex"


def opencode_home() -> Path:
    base = Path(os.environ["XDG_CONFIG_HOME"]).expanduser() if os.environ.get("XDG_CONFIG_HOME") else Path.home() / ".config"
    return base / "opencode"


def config_bytes(path: Path, *, in_repository: bool) -> bytes:
    """A harness config file's bytes, or OSError when aidd will not read it: a link inside the repository, anything
    but a regular file (a device or a pipe, which a read could hang on), or a file past HARNESS_CONFIG_MAX_BYTES. A
    link in the home folder may stand for a person's dotfile, so there only its target must be a regular file."""
    if in_repository and path.is_symlink():
        raise OSError(f"{path.name} is a link")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise OSError(f"{path.name} is not a regular file")
        data = f.read(HARNESS_CONFIG_MAX_BYTES + 1)
    if len(data) > HARNESS_CONFIG_MAX_BYTES:
        raise OSError(f"{path.name} is larger than {HARNESS_CONFIG_MAX_BYTES // 1024} KiB")
    return data


def read_toml(data: bytes) -> object:
    return tomllib.loads(data.decode("utf-8"))


def read_json(data: bytes) -> object:
    return json.loads(data.decode("utf-8"))


def _names(entry: object, folder: Path) -> bool:
    """Whether a config's path entry names `folder`. An entry no path can be read from (a NUL, an unknown `~user`)
    names nothing."""
    try:
        return isinstance(entry, str) and Path(entry).expanduser().resolve() == folder
    except (OSError, ValueError, RuntimeError):
        return False


def codex_git_check(root: Path) -> tuple[str, str]:
    """Whether a Codex run can write the git directory, where `aidd autopilot start` keeps its lease. Codex's
    `workspace-write` sandbox keeps `.git` read-only unless the folder is a writable root: `--add-dir`, which aidd
    cannot see, or `sandbox_workspace_write.writable_roots` in a config it reads."""
    found = git.run(["rev-parse", "--path-format=absolute", "--git-common-dir"], str(root), check=False).strip()
    gitdir = Path(found).resolve() if found else root.resolve() / ".git"
    for path in (root / ".codex" / "config.toml", codex_home() / "config.toml"):
        try:
            data = read_toml(config_bytes(path, in_repository=path.parent == root / ".codex"))
        except (OSError, ValueError, RecursionError):
            continue
        section = data.get("sandbox_workspace_write") if isinstance(data, dict) else None
        roots = section.get("writable_roots") if isinstance(section, dict) else None
        if isinstance(roots, list) and any(_names(r, gitdir) for r in roots):
            return ("ok", f"Codex may write the git directory, where the run keeps its lease ({path.name} lists it in `writable_roots`)")
    return (
        "warn",
        f"Codex's `workspace-write` sandbox keeps `.git` read-only, so `aidd autopilot start` cannot write its lease in "
        f"{gitdir / 'aidd'}: start Codex with `--add-dir {shlex.quote(str(gitdir))}`, or list that folder in "
        "`sandbox_workspace_write.writable_roots` in `.codex/config.toml`",
    )
