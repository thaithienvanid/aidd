"""A command that lands work on a branch, read as a merge: with no remote trunk, a commit, a cherry-pick, a revert, an am, a rebase, a
reset to a commit ahead, or a ref moved onto the default branch lands work there with no pull request, so it takes the level of
`git.merge` on that branch. Where a remote holds the trunk it lands nothing until a push, which asks on its own.

`commands.call_actions` adds `git.merge` to each such command, and `commands._reading` hands the branch it read to `commit_reading`,
which keeps the action only where the command is that merge. The branch is read as a merge's is: the session's, a branch a
checkout earlier on the line names, or the one the caller names. The trunk is read first, in the folder the command runs in,
`git -C <dir>` included, as the one reading of the trunk says (`git.trunk_is_remote`), so no way of writing the same commit makes it
ask where a remote takes the pull request. A `git commit-tree` moves no ref and stays allowed.
"""

from __future__ import annotations

import os
from pathlib import Path

from aidd.kernel import git, processes
from aidd.risk.shell import GIT_VALUE_OPTIONS, SETTING

_ELSEWHERE = ("--git-dir", "--work-tree")
# The commands that land commits on the branch checked out, and the options of each that end or show a run and land nothing.
_ON_HEAD = {
    "commit": frozenset(),
    "cherry-pick": frozenset({"--abort", "--quit", "--skip"}),
    "revert": frozenset({"--abort", "--quit", "--skip"}),
    "am": frozenset({"--abort", "--quit", "--skip", "--show-current-patch"}),
    "rebase": frozenset({"--abort", "--quit", "--skip", "--show-current-patch", "--edit-todo"}),
}
_FORCE_BRANCH = {"-f", "--force"}
_MOVE_BRANCH = {"-m", "-M", "-c", "-C", "--move", "--copy"}


def _split(simple: str) -> tuple[str, list[str]]:
    """The subcommand and the words after it of a `git` command, else an empty subcommand."""
    words = simple.split()
    return (words[1], words[2:]) if len(words) > 1 and words[0] == "git" else ("", [])


def named_target(simple: str) -> str | None:
    """The branch a command moves by naming it, as a push names its target: `git branch -f|-m|-M|-c|-C <name>`, `git checkout -B` and
    `git switch -C <name>`, `git update-ref refs/heads/<name> <new>`, and `git fetch <repo> <src>:<name>`. None for any other."""
    sub, rest = _split(simple)
    names = [w for w in rest if not w.startswith("-")]
    options = {w.split("=")[0] for w in rest if w.startswith("-")}
    if sub == "branch" and names:
        if options & _FORCE_BRANCH:
            return names[0]
        return names[-1] if options & _MOVE_BRANCH else None
    if (sub == "checkout" and "-B" in options) or (sub == "switch" and options & {"-C", "--force-create"}):
        return names[0] if names else None
    if sub == "update-ref" and "-d" not in options:
        return next((w.removeprefix("refs/heads/") for w in names if w.startswith("refs/heads/")), None)
    if sub == "fetch":
        return next((w.split(":", 1)[1].removeprefix("refs/heads/") for w in names if ":" in w.lstrip("+")), None)
    return None


def lands_work(simple: str) -> bool:
    """Whether a command lands work on a branch: a commit, a cherry-pick, a revert, an am, a rebase, a reset that is no `--hard`, or a
    ref moved onto a branch it names. A run that ends or shows (`--abort`, `--quit`, `--show-current-patch`) lands nothing."""
    sub, rest = _split(simple)
    if sub in _ON_HEAD:
        return not set(rest) & _ON_HEAD[sub]
    return (sub == "reset" and "--hard" not in rest) or named_target(simple) is not None


def commit_folder(call: str, folder: str | None) -> str | None:
    """The folder a git command runs in: `folder`, moved by each `git -C <dir>` before the subcommand, a relative one from the last.
    None when aidd cannot tell: no folder and no absolute `-C`, a `-C` target that is no folder or holds a variable or `~`, or a
    repository named another way (`--git-dir`, `--work-tree`, `GIT_DIR=`, `GIT_WORK_TREE=`)."""
    try:
        words = processes.split_words(call)
    except ValueError:
        words = call.split()
    i = 0
    while i < len(words) and SETTING.fullmatch(words[i]):
        if words[i].startswith(("GIT_DIR=", "GIT_WORK_TREE=")):
            return None
        i += 1
    if words[i : i + 1] and words[i].rsplit("/", 1)[-1] != "git":
        return folder
    here = folder
    i += 1
    while i < len(words) and words[i].startswith("-"):
        word = words[i]
        i += 1
        if word.startswith(_ELSEWHERE):
            return None
        if word == "-C" and i < len(words):
            target = words[i]
            i += 1
            if any(c in target for c in "$`~") or (here is None and not os.path.isabs(target)) or not os.path.isdir(Path(here or "/") / target):
                return None
            here = str((Path(here or "/") / target).resolve())
        elif word in GIT_VALUE_OPTIONS:
            i += 1
    return here


def _reset_lands(rest: list[str], folder: str) -> bool:
    """Whether a `git reset` that is no `--hard` moves the branch to a commit that is no rewind: one that is not HEAD and not behind it.
    `git reset HEAD <file>`, `git reset --soft` with no commit, and `git reset HEAD~1` land nothing."""
    head = git.run(["rev-parse", "--verify", "-q", "HEAD"], folder, check=False).strip()
    for word in (w for w in rest if not w.startswith("-")):
        rev = git.run(["rev-parse", "--verify", "-q", f"{word}^{{commit}}"], folder, check=False).strip()
        if rev:
            return rev != head and not git.ok(["merge-base", "--is-ancestor", rev, "HEAD"], folder)
    return False


def commit_reading(simple: str, where: str | None, folder: str | None) -> tuple[str | None, list[str]] | None:
    """The reading of a command that lands work (`lands_work`) as a merge: None where it lands nothing (a remote holds the trunk, or
    the branch is not the default), `default` where it lands on the default branch, and `(None, [])` where the branch cannot be read,
    which is the strictest level, as for a merge. `where` is the branch checked out, as a rule names it. `folder` is the repository
    the command runs in (`commit_folder`), or None when aidd cannot read it, so the trunk cannot be looked up."""
    if folder is not None and git.trunk_is_remote(folder):
        return None
    if (target := named_target(simple)) is not None:
        if folder is None:
            return None, []
        return ("default", []) if target in git.default_branches(folder)[0] else None
    sub, rest = _split(simple)
    if sub == "reset" and folder is not None and not _reset_lands(rest, folder):
        return None
    if where is None:
        return None, []
    return ("default", []) if where == "default" else None
