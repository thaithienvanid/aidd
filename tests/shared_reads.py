"""Shared git reads for a table of rows that only read one repository.

aidd's own answer to a command line already reads each ref and setting once (`aidd.kernel.git_reads.shared_reads`). This module
holds that one scope open over a whole table, or a whole class, so a row costs its answer and not the git children the
last row already ran. It is safe only while the repository's refs, HEAD, and config do not change, so each use checks that
they did not at every git call aidd makes and at its end, and fails when they did, even if a test undid the change before it ended.
"""

from __future__ import annotations

import contextlib
import os
import re
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  # puts src/ on sys.path and makes the run hermetic

from aidd.kernel import git as kernel_git
from aidd.kernel import git_reads


INCLUDE_PATH = re.compile(r"^\s*path\s*=\s*(.+?)\s*$", re.MULTILINE)
INCLUDE_SECTION = re.compile(r"^\s*\[include(?:If\s+[^\]]*)?\]", re.MULTILINE | re.IGNORECASE)


def config_files(root) -> list[Path]:
    """The config files git reads for the repository at `root`, as git finds them from this process's environment: the
    repository's, the person's global (`GIT_CONFIG_GLOBAL`, else `~/.gitconfig` and the XDG one), and the system one."""
    env = os.environ
    home = Path(env.get("HOME", "~")).expanduser()
    xdg = Path(env.get("XDG_CONFIG_HOME") or home / ".config")
    first = [Path(root) / ".git" / "config", Path(env["GIT_CONFIG_GLOBAL"]) if "GIT_CONFIG_GLOBAL" in env else home / ".gitconfig", xdg / "git" / "config"]
    if env.get("GIT_CONFIG_SYSTEM") or "GIT_CONFIG_NOSYSTEM" not in env:
        first.append(Path(env.get("GIT_CONFIG_SYSTEM", "/etc/gitconfig")))
    return first


def included(path: Path) -> list[Path]:
    """The files that the `path` lines of the include sections in the config file at `path` name."""
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    if not INCLUDE_SECTION.search(text):
        return []
    named = (Path(value.strip('"')).expanduser() for value in INCLUDE_PATH.findall(text))
    return [name if name.is_absolute() else path.parent / name for name in named]


def object_marks(git_dir: Path) -> dict[str, bytes]:
    """When each object folder last changed, which an object written by a command no ref names moves: `hash-object -w` and an unreferenced commit."""
    marks = {}
    objects = git_dir / "objects"
    if objects.is_dir():
        for entry in os.scandir(objects):
            if entry.is_dir():
                marks[f"objects/{entry.name}"] = str(entry.stat().st_mtime_ns).encode()
    return marks


def ref_state(root) -> dict[str, bytes]:
    """What the guard watches in the repository at `root`, by name with its bytes: the repository's config, HEAD, packed refs,
    every ref, and its own attributes file; the person's global and system config and every file an include section names, up to three levels
    down, at their paths; and the change time of each object folder, so an object that no ref names is seen. It does not watch the
    index or the work tree, which no kept read depends on, nor the environment, which the kept reads are keyed by, nor an `includeIf` condition, whose files it watches whether or not the condition matches."""
    git_dir = Path(root) / ".git"
    named = [git_dir / "HEAD", git_dir / "packed-refs", git_dir / "info" / "attributes"]
    named += sorted(p for p in (git_dir / "refs").rglob("*") if p.is_file())
    state = {str(p.relative_to(git_dir)): p.read_bytes() for p in named if p.is_file()}
    pending, seen = config_files(root), set()
    for _ in range(3):
        later = []
        for path in pending:
            if path not in seen:
                seen.add(path)
                if path.is_file():
                    state[f"config:{path}"] = path.read_bytes()
                later += included(path)
        pending = later
    return {**state, **object_marks(git_dir)}


def changed_names(before: dict[str, bytes], after: dict[str, bytes]) -> list[str]:
    return sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))


@contextlib.contextmanager
def shared_git_reads(root):
    """aidd reads each ref and setting of the repository at `root` once inside the block. The block fails when the config,
    HEAD, or a ref differs from the start at any git call aidd makes in it, or at its end: a write that a test undoes before
    the end would else leave a read between the two answering for a state that no longer held. A test that writes between its
    rows keeps its own reads and never uses a block."""
    before = ref_state(root)
    violations: list[str] = []
    real, local = kernel_git._git, kernel_git._LOCAL

    def guarded(args, cwd=".", call=local):
        if changed := changed_names(before, ref_state(root)):
            violations.append(f"the repository changed inside shared_git_reads before `git {' '.join(args)}`, so a kept read would have been stale: {changed}")
            raise AssertionError(violations[-1])
        return real(args, cwd, call)

    with mock.patch.object(kernel_git, "_git", guarded), git_reads.shared_reads():
        yield
        if changed := changed_names(before, ref_state(root)):
            violations.append(f"the repository changed inside shared_git_reads, so its later reads were stale: {changed}")
    if violations:
        raise AssertionError(violations[0])


class ReadOnlyRepoCase(unittest.TestCase):
    """A repository that every test of the class only reads. `setUpClass` builds it at `cls.root` and calls `cls.share_reads()`,
    so aidd's git reads are shared for the whole class. A test that changes the refs, HEAD, or config fails, at its end or at the next git call aidd makes."""

    root: str
    _kept_state: dict[str, bytes]

    @classmethod
    def share_reads(cls) -> None:
        stack = contextlib.ExitStack()
        stack.enter_context(shared_git_reads(cls.root))
        cls.addClassCleanup(stack.close)
        cls._kept_state = ref_state(cls.root)

    def setUp(self):
        super().setUp()
        self.addCleanup(self._fail_if_changed)

    def _fail_if_changed(self) -> None:
        if ref_state(self.root) != self._kept_state:
            raise AssertionError(f"{self.id()} changed the repository's refs, HEAD, or config inside the class's shared reads")
