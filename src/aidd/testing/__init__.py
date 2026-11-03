"""`aidd test`: run a change's tests, green on the head and, for new behavior, red on the base, and write the evidence.

The child: runner. This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["red_ok", "required_tests", "run_test_command", "run_tests", "select_tests", "watch_tests", "worktree_slug"]

if TYPE_CHECKING:
    from aidd.testing.runner import red_ok as red_ok
    from aidd.testing.runner import required_tests as required_tests
    from aidd.testing.runner import run_test_command as run_test_command
    from aidd.testing.runner import run_tests as run_tests
    from aidd.testing.runner import select_tests as select_tests
    from aidd.testing.runner import watch_tests as watch_tests
    from aidd.testing.runner import worktree_slug as worktree_slug
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "red_ok": "runner",
            "required_tests": "runner",
            "run_test_command": "runner",
            "run_tests": "runner",
            "select_tests": "runner",
            "watch_tests": "runner",
            "worktree_slug": "runner",
        },
    )
