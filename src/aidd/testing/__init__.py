"""`aidd test`: run a change's tests, green on the head and, for new behavior, red on the base, and write the evidence.

The child: runner. This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "EVIDENCE_MAX_BYTES",
    "MAX_SPECS",
    "Governing",
    "GoverningChange",
    "base_frozen_problem",
    "change_branch",
    "exit_code",
    "find_governing",
    "last_run_summary",
    "ran_nothing",
    "red_ok",
    "result_mark",
    "run_test_command",
    "run_tests",
    "tests_apply",
    "watch_tests",
]

if TYPE_CHECKING:
    from aidd.testing.base_frozen import base_frozen_problem as base_frozen_problem
    from aidd.testing.governing import Governing as Governing
    from aidd.testing.governing import GoverningChange as GoverningChange
    from aidd.testing.governing import change_branch as change_branch
    from aidd.testing.governing import find_governing as find_governing
    from aidd.testing.last_run import EVIDENCE_MAX_BYTES as EVIDENCE_MAX_BYTES
    from aidd.testing.last_run import MAX_SPECS as MAX_SPECS
    from aidd.testing.last_run import last_run_summary as last_run_summary
    from aidd.testing.runner import red_ok as red_ok
    from aidd.testing.runner import run_test_command as run_test_command
    from aidd.testing.runner import run_tests as run_tests
    from aidd.testing.runner import tests_apply as tests_apply
    from aidd.testing.verdict import exit_code as exit_code
    from aidd.testing.verdict import ran_nothing as ran_nothing
    from aidd.testing.verdict import result_mark as result_mark
    from aidd.testing.watching import watch_tests as watch_tests
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "EVIDENCE_MAX_BYTES": "last_run",
            "MAX_SPECS": "last_run",
            "Governing": "governing",
            "GoverningChange": "governing",
            "base_frozen_problem": "base_frozen",
            "change_branch": "governing",
            "exit_code": "verdict",
            "find_governing": "governing",
            "last_run_summary": "last_run",
            "ran_nothing": "verdict",
            "red_ok": "runner",
            "result_mark": "verdict",
            "run_test_command": "runner",
            "run_tests": "runner",
            "tests_apply": "runner",
            "watch_tests": "watching",
        },
    )
