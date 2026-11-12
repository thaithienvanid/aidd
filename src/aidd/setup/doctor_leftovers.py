"""`aidd doctor`'s notes on what a run left open on this machine: a worktree, a branch, and a scratch folder, each a row of the
machine class in `schemas/lifecycles.json`, whose `close_with` gives the step each note names.

A worktree or a branch is left over when every commit it holds is on the branch checked out here or on the default branch.
Git answers that, never aidd: `git cherry <target> <head>` marks each commit of the head with `-` when the target holds a
commit with the same patch, and `+` when it holds none, so a commit brought over by a cherry-pick counts as on the target. A
commit brought over with a conflict resolved has another patch, so git marks it `+`, and that worktree or branch is never
named: a reviewer checks it first. A scratch folder under `.aidd/tmp/` is left over when nothing in it changed for
SCRATCH_AGE_DAYS. Doctor reads only, removes nothing, and says nothing when nothing is left over.

A branch name or a path is the repository's text, so it is data: a fetched branch or a hostile repository may name one
with `;`, `$(...)`, a quote, a line break, or a control character. Every name a note shows goes through `documents.one_line`,
and a name joins a command only by the one rule in `kernel.command_names`: a plain name, quoted, after `--`; any other name gets
no command at all."""

from __future__ import annotations

import os
import re
import stat
import time
from pathlib import Path

from aidd.kernel import command_names, documents, git, resources

# A scratch folder nobody changed for this many days is no trial in progress: a run makes a new folder for each trial.
SCRATCH_AGE_DAYS = 7
SCRATCH_DIR = ".aidd/tmp"
# The most branches with no worktree that doctor asks git about one by one, newest first, so a repository that keeps many
# old branches stays fast. A branch merged by ancestry costs no call of its own.
MAX_BRANCH_CHECKS = 100
# A commit id as git prints it: SHA-1 or SHA-256 in hex.
COMMIT_ID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def close_step(thing: str, name: str) -> str:
    """How to close `thing`, as its row in schemas/lifecycles.json gives it in `close_with`. A command takes `name` for its
    one `<...>` part, by the rule of `command_names` (a plain name, quoted, after `--`); for any other name the step says to
    remove it by hand, and the command never holds the name."""
    step = str(resources.load_json("lifecycles.json")["things"][thing]["close_with"])
    hole = re.search(r"<[a-z]+>", step)
    if hole is None:
        return step
    word = command_names.quoted(name)
    if word is None:
        return f"remove it by hand: {command_names.NO_COMMAND}"
    return f"`{step[: hole.start()]}{word}{step[hole.end() :]}`"


def _place(root: Path, path: str) -> str:
    """A path as a note and its command take it: from the repository's top when it is inside it, else as git gave it."""
    p = Path(path)
    return p.relative_to(root).as_posix() if p.is_relative_to(root) else path


def _shown(name: str) -> str:
    """A name from the repository as a note shows it: on one line, with no control or direction character, cut to a length.
    A backtick shows as a quote, so no part of a name reads as a command span of the note."""
    return documents.one_line(name, 300).replace("`", "'")


def _worktrees(root: Path) -> list[dict[str, str]]:
    """Each worktree git lists, the main one first, from `git worktree list --porcelain -z`: its `worktree` path, its `HEAD`,
    its `branch` when one is checked out, and `bare`, `locked`, or `prunable` when git marks it so."""
    out: list[dict[str, str]] = []
    # `-z` ends each line with NUL, so a path that holds a line break stays one path.
    for block in git.run(["worktree", "list", "--porcelain", "-z"], str(root)).split("\0\0"):
        entry: dict[str, str] = {}
        for line in block.split("\0"):
            key, _, value = line.partition(" ")
            entry[key] = value
        if entry.get("worktree"):
            out.append(entry)
    return out


def _on_target(root: Path, head: str, targets: list[str]) -> str | None:
    """The first target that holds every commit of `head`, by git's patch match (`git cherry`), else None. A head git
    cannot read is on no target."""
    for target in targets:
        try:
            listed = git.run(["cherry", target, head], str(root))
        except git.GitError:
            continue
        if not any(line.startswith("+") for line in listed.splitlines()):
            return target
    return None


def _targets(root: Path) -> tuple[list[str], set[str]]:
    """The branches a left-over commit may sit on, the one checked out here and then the default branch, and the names
    doctor never calls left over: those, and each name the default branch may have."""
    current = git.current_branch(str(root))
    try:
        default = git.default_base(str(root))
    except git.GitError:
        default = ""
    targets = list(dict.fromkeys(t for t in (current, default) if t))
    return targets, {*targets, *git.default_branches(str(root))[0]}


def worktree_lines(root: Path, targets: list[str], worktrees: list[dict[str, str]]) -> list[tuple[str, str]]:
    """A note for each worktree, other than the main one and this one, whose every commit is on a target."""
    out = []
    here = root.resolve()
    for entry in worktrees[1:]:
        path = entry["worktree"]
        # The head is git's commit id, never text that could reach git as an option.
        if Path(path).resolve() == here or {"bare", "locked", "prunable"} & set(entry) or not COMMIT_ID.fullmatch(entry.get("HEAD", "")):
            continue
        if target := _on_target(root, entry["HEAD"], targets):
            branch = entry.get("branch", "").removeprefix("refs/heads/")
            place = _place(root, path)
            named = f" (branch {_shown(branch)})" if branch else ""
            out.append(
                (
                    "note",
                    f"left open: the worktree {_shown(place)}{named} has every commit on {_shown(target)}. Once its role is done, "
                    f"{close_step('worktree', place)}; git refuses to remove a worktree with changes not committed",
                )
            )
    return out


def branch_lines(root: Path, targets: list[str], kept: set[str], worktrees: list[dict[str, str]]) -> list[tuple[str, str]]:
    """A note for each local branch that no worktree has checked out and whose every commit is on a target, except the
    branches in `kept`."""
    checked_out = {e["branch"].removeprefix("refs/heads/") for e in worktrees if e.get("branch")}
    names = git.run(["for-each-ref", "--sort=-committerdate", "--format=%(refname:short)", "refs/heads"], str(root)).split()
    loose = [n for n in names if n not in checked_out and n not in kept]
    merged: dict[str, str] = {}
    for target in targets:
        for name in git.run(["for-each-ref", f"--merged={target}", "--format=%(refname:short)", "refs/heads"], str(root)).split():
            merged.setdefault(name, target)
    for name in [n for n in loose if n not in merged][:MAX_BRANCH_CHECKS]:
        if picked := _on_target(root, f"refs/heads/{name}", targets):
            merged[name] = picked
    out = []
    for name in loose:
        if name in merged:
            out.append(
                (
                    "note",
                    f"left open: the branch {_shown(name)} has no worktree and every commit on {_shown(merged[name])}. Once its change "
                    f"merged, {close_step('branch', name)}; deleting a branch asks first, because it is a person's step",
                )
            )
    return out


def _newest_change(folder: Path) -> float:
    """The latest time the folder or an entry directly in it changed, read without following a link."""
    newest = os.lstat(folder).st_mtime
    with os.scandir(folder) as entries:
        for entry in entries:
            newest = max(newest, entry.stat(follow_symlinks=False).st_mtime)
    return newest


def scratch_lines(root: Path, now: float | None = None) -> list[tuple[str, str]]:
    """A note for each folder directly in `.aidd/tmp/` in which nothing changed for SCRATCH_AGE_DAYS. A link is no folder."""
    base = root / SCRATCH_DIR
    try:
        if not stat.S_ISDIR(os.lstat(base).st_mode):
            return []
        with os.scandir(base) as found:
            folders = sorted((e.path for e in found if e.is_dir(follow_symlinks=False)), key=os.path.basename)
    except OSError:
        return []
    now = time.time() if now is None else now
    out = []
    for folder in folders:
        try:
            days = int((now - _newest_change(Path(folder))) // 86400)
        except OSError:
            continue
        if days >= SCRATCH_AGE_DAYS:
            out.append(
                (
                    "note",
                    f"left open: the scratch folder {_shown(_place(root, folder))} has not changed for {days} days: {close_step('scratch_folder', '')}",
                )
            )
    return out


def leftover_lines(root: Path) -> list[tuple[str, str]]:
    """Every note on what a run left open here: the worktrees, then the branches, then the scratch folders."""
    try:
        worktrees = _worktrees(root)
        targets, kept = _targets(root)
        found = worktree_lines(root, targets, worktrees) + branch_lines(root, targets, kept, worktrees) if targets else []
    except git.GitError:
        found = []
    return found + scratch_lines(root)
