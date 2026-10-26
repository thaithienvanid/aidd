"""Autopilot's actions in one harness's words (`aidd autopilot next --harness KEY`): each team command as that harness
runs it, the file that holds it, and no `/aidd <verb>` where the harness has none.

The engine names a team command as the aidd-team plugin does (`/aidd-team:implement`). In a harness the flow runs as a
repository file, the same command is `/aidd-implement`, or `$aidd-implement` in Codex, and the lead reads it from the
file `aidd init --team` wrote (`setup.flow_command_file`). The `/aidd <verb>` commands (`/aidd land`) exist only where
aidd-mods (Claude Code) or OpenCode's aidd-tui runs them; elsewhere a person types the words instead.
"""

from __future__ import annotations

import re
from pathlib import Path

# The harnesses whose rendered autopilot flow passes `--harness`: Claude Code and each harness with flow commands.
HARNESSES = ("claude-code", "codex", "opencode", "grok-build", "antigravity")
# Where `/aidd <verb>` runs: Claude Code's aidd-mods plugin, and OpenCode's aidd-tui (AGENTS.md, "Every harness behaves the same").
VERBS = frozenset({"claude-code", "opencode"})
_PLUGIN_COMMAND = re.compile(r"/aidd-team:([a-z][a-z-]*)")
_VERB = re.compile(r" \(or `/aidd [^`]+`\)")
_CLEAR = " (or `/clear`)"
_TEXT = ("command", "why", "what", "how", "message", "resume")


def flow_form(root: Path, harness: str, flow: str) -> tuple[str, str | None]:
    """(what the lead types for team command `flow` in `harness`, the file that holds it, or None for the plugin's)."""
    from aidd import setup

    path = setup.flow_command_file(harness, flow)
    if harness == "claude-code" and not (path and (root / path).is_file()):
        return f"/aidd-team:{flow}", None  # the aidd-team plugin's command, in its own folder
    return setup.flow_command_name(harness, flow), path


def in_harness(action: dict, root: Path, harness: str) -> dict:
    """`action` with every team command it names in `harness`'s form, a `file` beside each `run` of a team flow, and
    no `/aidd <verb>` or `/clear` the harness lacks."""

    def said(text: str) -> str:
        text = _PLUGIN_COMMAND.sub(lambda m: flow_form(root, harness, m.group(1))[0], text)
        text = text if harness in VERBS else _VERB.sub("", text)
        return text if harness == "claude-code" else text.replace(_CLEAR, "")

    def one(item: dict) -> dict:
        out = {k: said(v) if k in _TEXT and isinstance(v, str) else v for k, v in item.items()}
        if out.get("flow"):
            file = flow_form(root, harness, str(out["flow"]))[1]
            out |= {"file": file} if file else {}
        return out

    out = one(action)
    for key in ("also", "decisions"):
        if action.get(key):
            out[key] = [one(x) for x in action[key]]
    return out
