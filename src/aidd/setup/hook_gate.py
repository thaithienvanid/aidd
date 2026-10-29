"""The shell check that runs before the post-tool hook starts Python (`aidd hook post-tool`).

PostToolUse fires for every tool call of every agent, but only an aidd-team role's calls are counted
(`guard.turn_budget`). The check reads the event in POSIX sh and ends the hook, silently and at once, unless the event
names an agent type that starts with `aidd-`, written as `"agent_type":"aidd-` (or with one space after the colon) (`aidd-team:<role>` from the plugin, `aidd-<role>` from `aidd init --team`).
So the lead and every helper cost one `sh`, not a Python start. It only decides whether to go on: it never evals the
event, and a miss costs nothing but a line the role would have read (Python checks the type again, in full). Only the two exact forms
are matched, so the check stays linear on an event with many `agent_type` keys (a looser pattern took seconds under macOS's sh). It reads the event with `/bin/cat`, a program no project folder on PATH can stand in for (where it is
missing the hook ends, and a role simply gets no line). The event is passed on through a pipe, so the launcher behind it reads it as before.
"""

from __future__ import annotations

import re

POST_TOOL_GATE = (
    """unset -f printf 2>/dev/null; E=$(/bin/cat); case $E in *'"agent_type":"aidd-'*|*'"agent_type": "aidd-'*) ;; *) exit 0;; esac; printf '%s' "$E" | """
)
POST_TOOL_GATE_PATTERN = re.escape(POST_TOOL_GATE)


def portable_hook(subs: str) -> re.Pattern[str]:
    """The user launcher's command for one of the hooks `subs` names, with the check before it for the post-tool hook."""
    return re.compile(f"(?:{POST_TOOL_GATE_PATTERN})?" + r'"\$HOME"/\.aidd/bin/aidd hook (' + subs + r")(?: \|\| .*)?")
