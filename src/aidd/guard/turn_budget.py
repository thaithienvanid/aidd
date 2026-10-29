"""A wrap-up before an aidd-team role reaches its turn cap (`aidd hook post-tool`, Claude Code's PostToolUse).

A subagent is never told how many turns it has used. At its `maxTurns` cap Claude Code returns its output marked
partial, and the handoff note the loop needs is lost. Every aidd-team role has a cap (`max_turns` in
`schemas/roles.json`, written into its agent file), so this hook counts the tool calls of each role, and adds one line to
what the role reads next to a tool result:

- at 80% of its cap: finish the step, then write the handoff note and report what is left;
- at 95%: finish here, write the handoff note, and report what is left.

Each line comes once. A turn can hold several tool calls, so the count of calls is at least the count of turns and the
line comes early, never late. Claude Code sends `agent_id` and `agent_type` with a subagent's tool event
(code.claude.com/docs/en/hooks, checked 2026-10-29), and `hookSpecificOutput.additionalContext` reaches the subagent.
A harness whose events name no subagent (`Dialect.counts_turns`) gets nothing from this hook.

The count lives in the git directory, never in a working tree, as one small file for each subagent: one byte is appended
for each call (O_APPEND is atomic, so calls that run in parallel never lose a count), and the file's size is the count.
A line is claimed by creating a marker file (O_EXCL), so it comes once even when two calls cross the line together.
The first call of a role reads its cap from the team registry, and later calls read it from the file beside the count.
A call of anything but a role (the lead, a helper) costs one check of two fields and ends there.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from pathlib import Path

FIRST_SHARE, LAST_SHARE = 0.80, 0.95  # of a role's cap
FOLDER = "turns"
MAX_FILES = 600  # files kept in the folder (three or four for each subagent); the oldest go when a new subagent starts

CAP_ENV = "AIDD_HOOK_TURN_CAP"  # a cap for a live check (`aidd eval hooks`), set in the hook's own environment: it only lowers a role's cap

_OURS = re.compile(r"^[A-Za-z0-9_-]{1,80}\.(n|cap|80|95)$")  # the only names the folder holds, and the only ones pruned

ROLE_PREFIXES = ("aidd-team:", "aidd-")  # `aidd-team:<role>` from the plugin; `aidd-<role>` from `aidd init --team`


def wrap_up_line(used: int, cap: int) -> str:
    """The line at 80% of the cap."""
    return f"aidd: you have used about {used} of your {cap} turns. Finish the step you are on, then write your handoff note and report what is left."


def stop_line(left: int) -> str:
    """The line at 95% of the cap."""
    return f"aidd: about {left} turns are left. Finish here: write your handoff note and report what is left."


def thresholds(cap: int) -> tuple[int, int]:
    """(the call count at 80% of `cap`, the call count at 95%), each at least 1."""
    return max(1, math.ceil(cap * FIRST_SHARE)), max(1, math.ceil(cap * LAST_SHARE))


def _safe_id(agent_id: str) -> bool:
    return 0 < len(agent_id) <= 80 and agent_id.isascii() and all(c.isalnum() or c in "-_" for c in agent_id)


def _repo(cwd: str) -> str | None:
    """The nearest folder at or above `cwd` that holds the aidd config, by looking at the folders (no git call)."""
    here = Path(cwd).resolve()
    for folder in (here, *here.parents):
        if (folder / ".aidd" / "config.yaml").is_file():
            return str(folder)
    return None


def _count(folder: Path, agent_id: str) -> int:
    """Append one byte to the agent's count file, and give the file's size: the calls the agent has made, this one included."""
    fd = os.open(folder / f"{agent_id}.n", os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.write(fd, b".")
        return os.fstat(fd).st_size
    finally:
        os.close(fd)


def _claim(folder: Path, name: str) -> bool:
    """True the first time anyone claims `name`: the marker file is created, once."""
    try:
        os.close(os.open(folder / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600))
    except FileExistsError:
        return False
    return True


def _prune(folder: Path) -> None:
    """Drop the oldest of the folder's own files (a name `_OURS` reads, never a link) once it holds more than MAX_FILES."""
    try:
        found = [e for e in os.scandir(folder) if _OURS.match(e.name) and not e.is_symlink()]
        for _, path in sorted(((e.stat(follow_symlinks=False).st_mtime, e.path) for e in found), reverse=True)[MAX_FILES:]:
            os.unlink(path)
    except OSError:
        pass  # a count is a courtesy: it never fails a tool call


def _cap(folder: Path, agent_id: str, event: dict) -> int | None:
    """The turn cap of the role in `event`, from the file beside its count or (the first call) the team registry; None
    when the agent is not an aidd-team role."""
    path = folder / f"{agent_id}.cap"
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            return int(os.read(fd, 16).decode("ascii")) or None  # 0: not a role
        finally:
            os.close(fd)
    except (OSError, ValueError):
        pass
    from aidd import knowledge
    from aidd.guard.role_areas import role_of

    role = role_of(event)
    cap = knowledge.roles()["roles"][role].get("max_turns") if role else None
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1:
        cap = 0  # not a role, or a role with no cap: remembered, so the registry is read once
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as out:
            out.write(str(cap))
    except OSError:
        pass  # the cap is read from the registry again next time
    return cap or None


def due_line(folder: Path, agent_id: str, event: dict) -> str | None:
    """Count one tool call of the subagent, and give the line it is due, or None. The 95% line replaces the 80% one when
    the count has passed both."""
    used = _count(folder, agent_id)
    if used == 1:
        _prune(folder)
    cap = _cap(folder, agent_id, event)
    if cap is None:
        return None
    lowered = os.environ.get(CAP_ENV, "")
    cap = min(cap, int(lowered)) if lowered.isdigit() and int(lowered) >= 1 else cap
    first, last = thresholds(cap)
    if used >= last:
        _claim(folder, f"{agent_id}.80")  # past 80% too: that line is not said after this one
        return stop_line(max(0, cap - used)) if _claim(folder, f"{agent_id}.95") else None
    if used >= first and _claim(folder, f"{agent_id}.80"):
        return wrap_up_line(used, cap)
    return None


def post_tool(event: dict, stdout) -> int:
    """PostToolUse: the wrap-up lines for an aidd-team role (the module docstring). Nothing for any other call."""
    from aidd.guard import dialects

    agent_id, agent_type = event.get("agent_id"), event.get("agent_type")
    if not (isinstance(agent_id, str) and isinstance(agent_type, str) and agent_type.startswith(ROLE_PREFIXES) and _safe_id(agent_id)):
        return 0
    dialect = dialects.of(event)
    if not dialect.counts_turns:
        return 0
    cwd = event.get("cwd")
    root = _repo(cwd) if isinstance(cwd, str) and cwd else None
    if root is None:
        return 0
    from aidd import config
    from aidd.kernel import git

    with git.system_only():
        folder = config.state_dir(root) / FOLDER
    if folder.is_symlink():  # a link in the git directory could point the count anywhere: no count
        return 0
    folder.mkdir(parents=True, exist_ok=True)
    line = due_line(folder, agent_id, event)
    if line is None:
        return 0
    from aidd.guard import hook_settings

    cfg = hook_settings.load_config(root)
    if cfg is None or not hook_settings.enabled(cfg):
        return 0
    json.dump(dialect.context("PostToolUse", line), stdout)
    stdout.write("\n")
    return 0


def post_tool_hook(stdin=None, stdout=None, stderr=None) -> int:
    """`aidd hook post-tool`: read the event and give the line it is due. Any failure of its own allows: exit 0, nothing on
    stdout, and a short note on stderr. It never writes to the repository's working tree."""
    from aidd.guard import dialects, hook_capture

    stdin, stdout, stderr = stdin or sys.stdin, stdout or sys.stdout, stderr or sys.stderr
    try:
        raw = stdin.read()
        hook_capture.keep("post-tool", raw)  # under AIDD_HOOK_CAPTURE only
        event = json.loads(raw)
        if not isinstance(event, dict):
            return 0
        return post_tool(dialects.of(event).normalize(event), stdout)
    except Exception as exc:  # noqa: BLE001  # a count must never break the agent's session
        print(f"aidd hook post-tool: skipped after an internal error ({type(exc).__name__}); allowing", file=stderr)
        return 0
