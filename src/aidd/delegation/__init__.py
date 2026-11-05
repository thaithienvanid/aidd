"""A standing delegation: `aidd delegate check`, which says whether a delegated ask may go to the `aidd-team:delegate`
role, recomputed each time from git, the default branch's config, and the platform; the packet the delegate reads; its
answer; the stop; and the hook that answers Claude Code's prompt only for a verified answer.

The children: policy (the built-in data and the reason codes), commands (a command against its exact template),
diff_signals (the reserved paths, the deploying workflows, and the deleted test lines), local_run (the check's own
`aidd test` runs in a fresh worktree), platform (GitHub's facts, read only), check (the gates every action passes),
action_gates (each action's own gates), outcome (the run in order, its output, and its record), answers (the
packet, the answer, the stop, and the hook), and digest (what `aidd status` shows of what was decided).

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "DECIDED_BY",
    "PlatformError",
    "Request",
    "UsageError",
    "answer",
    "covered",
    "delegable",
    "digest_text",
    "hook_main",
    "packet",
    "reasons",
    "run_check",
    "stop",
]

if TYPE_CHECKING:
    from aidd.delegation.answers import answer as answer
    from aidd.delegation.answers import hook_main as hook_main
    from aidd.delegation.answers import packet as packet
    from aidd.delegation.answers import stop as stop
    from aidd.delegation.check import Request as Request
    from aidd.delegation.check import UsageError as UsageError
    from aidd.delegation.digest import digest_text as digest_text
    from aidd.delegation.outcome import run_check as run_check
    from aidd.delegation.platform import PlatformError as PlatformError
    from aidd.delegation.policy import DECIDED_BY as DECIDED_BY
    from aidd.delegation.policy import covered as covered
    from aidd.delegation.policy import delegable as delegable
    from aidd.delegation.policy import reasons as reasons
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "DECIDED_BY": "policy",
            "PlatformError": "platform",
            "Request": "check",
            "UsageError": "check",
            "answer": "answers",
            "covered": "policy",
            "delegable": "policy",
            "digest_text": "digest",
            "hook_main": "answers",
            "packet": "answers",
            "reasons": "policy",
            "run_check": "outcome",
            "stop": "answers",
        },
    )
