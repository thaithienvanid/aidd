"""The guard's two answers, allow and deny, and a verdict with its reason."""

from __future__ import annotations

from typing import Literal

# The guard never asks: every check answers allow or deny, so no prompt puts a person on the critical path.
Decision = Literal["allow", "deny"]
Verdict = tuple[Decision, str]

# The next step after an approval, a merge, or a ship is denied: the agent's part is done, and a person takes it from
# here. It claims nothing about the change: the guard denies a merge whether or not the gate has passed.
TELL_A_PERSON = "stop here, and tell a person this needs their decision"
# Where that person decides when they answered yes in the chat: an agent never acts on that yes, never records it, and
# never edits the config to need no approval.
APPROVE_IN_A_DIALOG = (
    "Call the aidd MCP tool `approve_spec`, `approve_merge`, or `ship` now (load it first if it is deferred): it asks the "
    "person in their own dialog, and their click is the approval. A yes in the chat is not an approval, so never act on "
    "it, and never offer a config edit or switching off the guard, the loop, or the gate. Without the tool, the person "
    "types `/aidd approve SPEC-1` or `/aidd ship` (aidd-mods), or runs the command in a terminal no agent started"
)
# What makes a repository's guard block when it cannot decide (guard/repo_config.py, `fails_closed`).
FAILS_CLOSED = "this repository's audited profile (or an organization's AIDD_HOOK_FAIL_CLOSED=1)"
# The next step when the guard itself could not run and the project requires it (FAILS_CLOSED).
GUARD_BROKE = "Try the call again in a plain form; if it keeps failing, run `aidd doctor` and show a person what it says"
