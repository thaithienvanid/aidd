"""What every harness's hook says when aidd's guard cannot run on this machine: one owner for the text that the
Claude Code launcher, the Codex, Grok Build, and Antigravity hook files, and the OpenCode plugin all carry."""

from __future__ import annotations

GET_STARTED = "https://github.com/thaithienvanid/aidd#get-started"


def guard_missing_message(setup: str) -> str:
    """What every harness's hook says when the guard cannot run on this machine: the warning, and the reason a project
    that fails closed denies with. A teammate who never installed aidd meets it first, so it starts there. Plain text
    that a shell's double quotes and a JSON string both carry as it is."""
    return (
        f"aidd: the guard could not run on this machine. Install aidd ({GET_STARTED}) if it is missing, then run {setup}; "
        "aidd doctor says why. A project that requires the guard blocks each step until then"
    )
