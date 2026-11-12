"""The checkout of the base for the red runs: in the repository itself, or in a worktree of its own.

The change's own tests ran first, so they may have added a program to the repository's config, such as a filter, that a
checkout starts. Every git call here that can start one gets `env`, the environment a test command gets, so that program
gets no credential-like variable in its environment that aidd removed from the test command's. The scrub is no boundary: the
program runs as the person and can still read aidd's own environment.
"""

from __future__ import annotations

import contextlib
import shutil
import tempfile
from collections.abc import Callable, Iterator

from aidd.kernel import command_names, git

# A required filter that needs a credential-like variable fails here, and git's own text never says why.
NEEDS_VARIABLE = (
    "aidd ran this checkout with the environment a test command gets, which has no credential-like variable. "
    "If a filter of this repository needs a variable, run `aidd test --pass-env NAME` with its name. If its program is missing, install it."
)


@contextlib.contextmanager
def _filter_note(restore: str = "") -> Iterator[None]:
    """A checkout whose filter fails stops with the next step too: `--pass-env`, and for an in-place checkout, how to restore the
    tracked files the failed checkout may have left missing."""
    try:
        yield
    except git.GitError as exc:
        if not git.is_filter_failure(exc):
            raise
        raise git.GitError(f"{exc}. {NEEDS_VARIABLE}{restore}") from exc


@contextlib.contextmanager
def checked_out(repo: str, commits: tuple[str, str], *, in_place: bool, env: dict[str, str], say: Callable[[str], None]) -> Iterator[str]:
    """The folder that holds the base's tree. In place, it is `repo` itself, and the branch it was on, or the head, is checked
    out again afterwards, discarding what the tests rewrote in tracked files, so the CI workspace keeps its installed
    dependencies. Otherwise it is a separate worktree, removed afterwards. `commits` is the base and the head."""
    base_sha, head_sha = commits
    if in_place:
        branch = git.current_branch(repo)
        say(f"checking out base {base_sha[:12]} in this checkout for the red runs, then back to {branch or head_sha[:12]}")
        ref = command_names.quoted(branch or head_sha)
        head = command_names.quoted(head_sha)  # a commit id is always safe to print
        again = (
            f"run `git checkout --force {ref}`"
            if ref
            else f"run `git checkout --force {head}`, then switch to your branch by its name"
            if head
            else "check out your branch by its name with `git checkout --force`"
        )
        restore = f" Tracked files may be missing from this checkout. Once the filter runs again in your own terminal, {again} to restore them."
        try:
            with _filter_note(restore):
                git.run(["checkout", "--quiet", "--force", "--detach", base_sha], repo, env=env)
            yield repo
        finally:
            back = ["checkout", "--quiet", "--force", "--end-of-options", branch] if branch else ["checkout", "--quiet", "--force", "--detach", head_sha]
            with _filter_note(restore):
                git.run(back, repo, env=env)
        return
    say(f"checking out base {base_sha[:12]} in a separate worktree for the red runs")
    tmp = tempfile.mkdtemp(prefix="aidd-red-")
    try:
        with _filter_note():
            git.run(["worktree", "add", "--detach", "--force", tmp, base_sha], repo, env=env)
        yield tmp
    finally:
        git.run(["worktree", "remove", "--force", tmp], repo, check=False)
        shutil.rmtree(tmp, ignore_errors=True)
