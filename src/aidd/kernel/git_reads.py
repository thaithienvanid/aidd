"""The scope in which aidd answers a git read once: `shared_reads`, what drops what it kept, and the key of an answer.

Inside a scope, `aidd.kernel.git` keeps each folder's blanks (filters and hooks) and each read a row of `git_forms` marks
`keeps`, by what was asked, where, and in which environment. A call that may write drops all of it, and so does
`forget_reads`, which a program aidd starts must call, because the scope sees only the git calls aidd makes itself.
"""

from __future__ import annotations

import contextlib
import contextvars
import os
from collections.abc import Iterator
from typing import Any

_SCOPE: contextvars.ContextVar[dict[tuple, Any] | None] = contextvars.ContextVar("git_shared_reads", default=None)


def current() -> dict[tuple, Any] | None:
    """What the open scope keeps, or None when no scope is open."""
    return _SCOPE.get()


def environment_key() -> tuple[tuple[str, str], ...]:
    """The whole environment of this process, as a key. Git reads its config files from `HOME`, `XDG_CONFIG_HOME`, and
    `GIT_CONFIG_*`, finds a repository by `GIT_DIR` and `GIT_CEILING_DIRECTORIES`, and picks its own program by `PATH`, so a
    kept answer is only the answer where the same environment asks again."""
    return tuple(sorted(os.environ.items()))


def forget_reads() -> None:
    """Drops what the open scope kept, if one is open. A program aidd starts, other than git, may write a repository, and the
    scope sees only the git calls aidd makes itself: call this after a test command or a plugin install that ran inside one."""
    if (kept := _SCOPE.get()) is not None:
        kept.clear()


@contextlib.contextmanager
def shared_reads() -> Iterator[None]:
    """Inside it, git reads each repository's filter and hook config once. It also runs each read in `kept_shape` once per
    folder and environment, with no environment or input of its caller's, then reuses the answer. A call that may write
    (`may_write`), such as a checkout or a commit, may change the refs or the config, so it clears what was kept, and so does
    `forget_reads`, which a program aidd starts must call. It is for the work of one command, such as one `command_level`, one
    `aidd doctor`, `aidd init`, `aidd status`, `aidd validate`, `aidd risk`, or `aidd test`, and never outlives it. A scope inside another shares the outer one's."""
    if _SCOPE.get() is not None:
        yield
        return
    token = _SCOPE.set({})
    try:
        yield
    finally:
        _SCOPE.reset(token)
