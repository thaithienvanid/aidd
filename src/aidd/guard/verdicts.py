"""The guard's two answers, allow and deny, and a verdict with its reason."""

from __future__ import annotations

from typing import Literal

# The guard never asks: every check answers allow or deny, so no prompt puts a person on the critical path.
Decision = Literal["allow", "deny"]
Verdict = tuple[Decision, str]

# The next step after an approval, a merge, a land, or a publish is denied: the agent's part is done, and a person takes it from
# here. It claims nothing about the change: the guard denies a merge whether or not the gate has passed.
TELL_A_PERSON = "stop here, and tell a person this needs their decision"
# Where that person decides when they answered yes in the chat: an agent never acts on that yes, never records it, and
# never edits the config to need no approval.
APPROVE_IN_A_DIALOG = (
    "Ask the person to type the decision at this prompt: `approve SPEC-1`, `land it`, `merge it`, or `approve all`, which aidd "
    "records from their own words. In Claude Code, call the aidd MCP tool `approve_spec`, `approve_merge`, `land`, or "
    "`publish` instead (load it first if it is deferred): it asks them in a dialog. Tell them `/aidd` lists every decision "
    "and its words. A yes in a sentence is not an approval, so never act on it, and never offer a config edit or "
    "switching off the guard, the loop, or the gate"
)
# What makes a repository's guard block when it cannot decide (guard/repo_config.py, `fails_closed`).
FAILS_CLOSED = "this repository's audited profile or `mode: enforce` (or an organization's AIDD_HOOK_FAIL_CLOSED=1)"
# The next step when the guard itself could not run and the project requires it (FAILS_CLOSED).
GUARD_BROKE = "Try the call again in a plain form; if it keeps failing, run `aidd doctor` and show a person what it says"
