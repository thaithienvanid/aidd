"""A standing delegation: `aidd delegate check`, which says whether a delegated ask may go to the `aidd-team:delegate`
role, recomputed each time from git, the default branch's config, and the platform; the packet the delegate reads; its
answer; the stop; and the hook that answers Claude Code's prompt only for a verified answer.

The children: policy (the built-in data and the reason codes), commands (a command against its exact template),
diff_signals (the reserved paths, the deploying workflows, and the deleted test lines), workflow_triggers (what a workflow's
`on:` says about a push, read fully or counted as unread), deploys (whether a push to a
branch deploys, and why), deploy_evidence (the environments the workflows name, for init and doctor), local_run (the check's own
`aidd test` runs in a fresh worktree), platform (GitHub's facts, read only), check (the checks every action passes),
action_checks (each action's own checks), parts (what the delegate reads, and its caps), text_checks (the tripwire,
the hidden characters, and the check that every text is held whole), independence (whether the delegate shares the author's
model), outcome (the run in order, its output, and its record), answers (the packet, the answer, the stop, and the hook),
digest (what `aidd status` shows of what was decided), and standing (whether the default branch holds the delegation).

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "DELEGATE_ANSWER_TOOLS",
    "DELEGATE_TOOLS",
    "Request",
    "answer",
    "digest_text",
    "hook_main",
    "not_yet_on_default_note",
    "packet",
    "read_deploy_evidence",
    "run_check",
    "same_model_warning",
    "stop",
    "undoable",
    "workflows_deploying_on",
]

if TYPE_CHECKING:
    from aidd.delegation.answers import answer as answer
    from aidd.delegation.answers import hook_main as hook_main
    from aidd.delegation.answers import packet as packet
    from aidd.delegation.answers import stop as stop
    from aidd.delegation.check import Request as Request
    from aidd.delegation.deploy_evidence import read_deploy_evidence as read_deploy_evidence
    from aidd.delegation.deploy_evidence import workflows_deploying_on as workflows_deploying_on
    from aidd.delegation.digest import digest_text as digest_text
    from aidd.delegation.independence import same_model_warning as same_model_warning
    from aidd.delegation.outcome import run_check as run_check
    from aidd.delegation.policy import DELEGATE_ANSWER_TOOLS as DELEGATE_ANSWER_TOOLS
    from aidd.delegation.policy import DELEGATE_TOOLS as DELEGATE_TOOLS
    from aidd.delegation.policy import undoable as undoable
    from aidd.delegation.standing import not_yet_on_default_note as not_yet_on_default_note
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "DELEGATE_ANSWER_TOOLS": "policy",
            "DELEGATE_TOOLS": "policy",
            "Request": "check",
            "answer": "answers",
            "digest_text": "digest",
            "hook_main": "answers",
            "not_yet_on_default_note": "standing",
            "packet": "answers",
            "read_deploy_evidence": "deploy_evidence",
            "run_check": "outcome",
            "same_model_warning": "independence",
            "stop": "answers",
            "undoable": "policy",
            "workflows_deploying_on": "deploy_evidence",
        },
    )
