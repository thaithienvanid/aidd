"""Where a written path lives: the repository that holds it (found from the path, never the session), each way the
file system may read it, and whether aidd governs it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from aidd import config
from aidd.guard import repo_config
from aidd.kernel import documents, git


def governed(root: str, rel: str) -> bool:
    """Repository content `delegate` governs: a path inside the repository, outside .git, that git tracks (a file, or a
    folder that holds one) or does not ignore. Scratch output in an ignored folder is not; a tracked file there is."""
    if not rel or rel == ".git" or rel.startswith((".git/", "../")) or os.path.isabs(rel):
        return False
    if git.ok(["--literal-pathspecs", "ls-files", "--error-unmatch", "--", rel], root):
        return True
    return not git.ok(["check-ignore", "-q", "--", rel], root)


@dataclass
class Place:
    """Where a path a tool writes lives: the top of the repository that holds it ("" outside every repository), why
    git failed there (None when it answered), the path relative to that top as it is spelled on disk, and the folder
    git was asked from."""

    top: str
    why: str | None
    rel: str
    probe: Path


def _probe(real: Path) -> Path:
    """The folder to ask git from for `real`: the folder that holds the `.git` on its way, since git answers no
    work-tree question from inside a git directory, else the nearest folder that exists (`real` itself for a folder)."""
    for i, part in enumerate(real.parts):
        if part.casefold() == ".git":
            return Path(*real.parts[:i])
    return next((p for p in (real, *real.parents) if p.is_dir()), Path(real.anchor))


def _relative(real: Path, base: Path) -> str | None:
    """`real` relative to `base`, also where a case-insensitive file system spells a folder on the way another way."""
    try:
        return real.relative_to(base).as_posix()
    except ValueError:
        pass
    for n in range(len(real.parts), 0, -1):
        head = Path(*real.parts[:n])
        try:
            if head.exists() and os.path.samefile(head, base):
                return Path(*real.parts[n:]).as_posix()
        except OSError:
            continue
    return None


def _disk_case(top: Path, rel: str) -> str:
    """`rel` with each part spelled as it is on disk, where a case-insensitive file system took another case
    (`BUILD/KEEP.txt` is build/keep.txt), so git's index and ignore checks and the globs read the file that is written."""
    cur, out = top, list[str]()
    parts = [p for p in rel.split("/") if p and p != "."]
    for i, part in enumerate(parts):
        try:
            names = os.listdir(cur)
        except OSError:
            return "/".join(out + parts[i:])
        if part not in names and os.path.lexists(cur / part):
            part = next((n for n in names if n.casefold() == part.casefold()), part)
        out.append(part)
        cur = cur / part
    return "/".join(out) or "."


def locate(path: Path) -> Place:
    """The repository that holds `path`, found from the path itself and never from the session's cwd, so a sibling or
    nested worktree, or a session started outside the repository, meets the same rules as an Edit. The path is read as
    the kernel reads it: each symbolic link is followed before the `..` after it (`out/l/../x` with `l` -> repo/src is
    repo/x), never with `..` taken away as text first."""
    real = Path(os.path.realpath(Path(path).absolute()))
    probe = _probe(real)
    top, why = repo_top(probe)
    if not top:
        return Place("", why, "", probe)
    base = Path(top).resolve()
    rel = _relative(real, base)
    if rel is None:
        return Place("", None, "", probe)
    return Place(top, None, _disk_case(base, rel), probe)


def readings(path: Path) -> list[Path]:
    """The files a tool may mean by `path`: as the kernel reads it, and, when that differs, with `..` taken away as text
    first, as a program that normalises a path before it opens it does. An edit tool's write is judged on both."""
    absolute = Path(path).absolute()
    textual = Path(os.path.normpath(absolute))
    return [absolute] if os.path.realpath(textual) == os.path.realpath(absolute) else [absolute, textual]


def config_problem(root: str | None) -> str | None:
    """Why an adopted repository's local config is invalid, said for the agent; None when it loads, or there is none.
    An invalid config never disables the guard: the callers hold the default commands and a role's writes on it. A URL
    parent the guard cannot fetch is expected (it runs offline by design): it is skipped with a warning, never a problem."""
    if not root or not repo_config.is_adopted(root):
        return None
    try:
        config.load_file(config.CONFIG_PATH, root, fetch=repo_config.offline_fetch, skip_unread=True)
        return None
    except (OSError, config.ConfigError, documents.DocumentError, RuntimeError, ValueError) as exc:
        text = str(exc).strip()
        first = text.splitlines()[0] if text else type(exc).__name__
        if "gated_commands" in text:
            first = "`guard.gated_commands` is now `guard.held_commands`: rename the key"
        return f"the aidd config is invalid: {first}; run `aidd validate`"


GIT_FAILED = (
    "the guard could not run git in this repository ({why}). It never reads a git failure as no repository where aidd "
    "is adopted, so it denies until git runs here. It runs only a git at {gits} that answers `git --version`, never one "
    "from the session's PATH. Run `aidd doctor` to see what fails"
)


def repo_top(probe: Path) -> tuple[str, str | None]:
    """(the repository's top level, or "" outside one; why git failed, or None when it answered)."""
    if not probe.is_dir():
        return "", None
    try:
        return git.toplevel(str(probe), check=True), None
    except git.GitError as exc:
        return "", str(exc)


def git_failed_reason(probe: Path, why: str | None) -> tuple[str, str] | None:
    """After git failed in `probe`: (the deny reason, the adopted folder) when the folder above it that holds the aidd
    config is a repository (it holds `.git`), so a git that cannot run or read it never turns the guard off; else None."""
    if why is None:
        return None
    start = probe.resolve()
    for d in (start, *start.parents):
        if repo_config.is_adopted(str(d)):
            if (d / ".git").exists():
                return GIT_FAILED.format(why=why.strip()[:300], gits=", ".join(git.SYSTEM_GITS)), str(d)
            return None
    return None


def session_root(cwd: Path) -> str | None:
    """The adopted repository the session works in (its cwd's), or None."""
    top, _ = repo_top(cwd)
    return top if top and repo_config.is_adopted(top) else None
