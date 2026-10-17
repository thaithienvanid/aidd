"""The PreToolUse hook (`aidd hook pre-tool`): read the event, decide, print a deny, and log it."""

from __future__ import annotations

import contextlib
import json
import os
import signal
import sys
import threading
from pathlib import Path

from aidd import workitems
from aidd.guard import (
    command_check,
    delegation,
    denial_log,
    dialects,
    edit_check,
    mcp_tools,
    path_location,
    repo_config,
    role_areas,
    verdicts,
    write_targets,
)
from aidd.kernel import git

# The guard decides within this time, under the 20-second timeout `aidd init` gives its hook: past that timeout,
# Claude Code lets the call through whatever the guard would say, so only a deadline of its own keeps the decision its.
DEADLINE_SECONDS = 15


class OutOfTime(BaseException):
    """The guard's deadline passed. A BaseException, so no `except Exception` on the way turns it into an answer."""


@contextlib.contextmanager
def _deadline(seconds: float):
    """Raise OutOfTime in this thread after `seconds`, where a POSIX timer can (the main thread); else no deadline."""
    if not hasattr(signal, "setitimer") or threading.current_thread() is not threading.main_thread():
        yield
        return

    def expire(signum, frame):
        raise OutOfTime

    previous = signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def pre_tool_hook(stdin=None, stdout=None, deadline_seconds: float = DEADLINE_SECONDS) -> int:
    """The PreToolUse hook of Claude Code and of Google Antigravity: reads the event JSON and prints a decision when it
    denies (Antigravity also gets an answer when it allows: no opinion, so the person's permission settings decide).

    It allows when it cannot tell: any failure of its own, or a check that runs past its deadline, exits 0 without a
    decision, never a block, unless AIDD_HOOK_FAIL_CLOSED=1 (the audited profile's managed settings) is set, when it is a deny.
    """
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    raw = ""
    try:
        with git.system_only(), _deadline(deadline_seconds):  # a git the session's PATH or GIT_* names never answers for the guard
            raw = stdin.read()
            return _pre_tool(raw, stdout)
    except OutOfTime:
        return _broke(stdout, raw, f"the guard could not check this tool call within {deadline_seconds:g} seconds")
    except Exception as exc:  # noqa: BLE001  # the guard's own crash allows, unless the organization requires the guard
        return _broke(stdout, raw, f"the guard could not check this tool call ({type(exc).__name__})")


def _broke(stdout, raw: str, what: str) -> int:
    """The guard could not decide: no decision, or a deny when AIDD_HOOK_FAIL_CLOSED=1 requires the guard; each in the
    format of the harness that sent `raw`."""
    event: dict = {}
    try:
        loaded = json.loads(raw)
        event = loaded if isinstance(loaded, dict) else {}
        dialect = dialects.of(event)
    except ValueError:
        dialect = dialects.CLAUDE_CODE
    # Fail-closed only where the project asks for it: a project that never adopted aidd is never blocked by it.
    if _fails_closed(event):
        return _answer(stdout, dialect, "deny", f"{what}, and {verdicts.FAILS_CLOSED} requires the guard. {verdicts.GUARD_BROKE}")
    return _answer(stdout, dialect, "allow", "")


def _fails_closed(event: dict) -> bool:
    """repo_config.fails_closed for the event's repository; the organization's setting alone when the guard cannot
    tell where it is."""
    try:
        top, _ = path_location.repo_top(Path(event.get("cwd") or "."))
    except Exception:  # noqa: BLE001  # when the guard cannot even tell where it is, the organization's rule holds
        return repo_config.fails_closed(None)
    return bool(top) and repo_config.fails_closed(top)


def _decide(stdout, decision: str, reason: str, root: str | None = None, event: dict | None = None) -> int:
    """Answer the harness that sent `event`; a deny is logged in `root` first."""
    if decision != "allow" and root and event is not None:
        try:
            denial_log.log_denial(root, event, reason)
        except Exception:  # noqa: BLE001  # the log is a convenience: it must never turn a deny into an allow
            pass
    return _answer(stdout, dialects.of(event), decision, reason)


def _answer(stdout, dialect: dialects.Dialect, decision: str, reason: str) -> int:
    """The decision in `dialect`'s format: a deny with its reason, or an allow as the harness's "no opinion", which
    leaves the call to the person's permission settings."""
    answer = dialect.no_opinion() if decision == "allow" else dialect.decision(decision, reason)
    if answer is not None:
        json.dump(answer, stdout)
    return 0


def _pre_tool(raw: str, stdout) -> int:
    try:
        event = json.loads(raw)
    except ValueError:
        return _broke(stdout, raw, "the guard could not read the tool call")
    if not isinstance(event, dict):
        raise TypeError("the hook event is not a JSON object")
    event = dialects.of(event).normalize(event)
    cwd = Path(event.get("cwd") or ".")
    tool_name, tool_input = str(event.get("tool_name") or ""), event.get("tool_input") or {}
    if tool_name.startswith("mcp__") or tool_name in denial_log.SHELL_TOOLS:  # PowerShell commands get the same checks as Bash
        top, why = path_location.repo_top(cwd)
        failed = None if top else path_location.git_failed_reason(cwd, why)
        if failed:
            return _decide(stdout, "deny", failed[0], failed[1], event)
        # The session's own repository, when it adopted aidd. Outside one, only the writes are checked: each in the
        # repository that holds its target.
        root = top if top and repo_config.is_adopted(top) else None
        if tool_name.startswith("mcp__"):
            decision, reason = mcp_tools.check_mcp_tool(tool_name, tool_input) if root else ("allow", "not an aidd repository")
            if decision == "allow":
                decision, reason = delegation.delegate_mcp(root, str(cwd), tool_name, tool_input, event) or (decision, reason)
            return _decide(stdout, decision, reason, root, event)
        command = tool_input.get("command") or ""
        if not command:
            return _decide(stdout, "allow", "", root, event)
        try:
            verdict = command_check.check_command(root, str(cwd), command, event)
        except Exception as exc:  # a parse that breaks never turns into an allow for a writer the guard holds
            if not (role_areas.role_of(event) or role_areas.is_helper(event) or delegation.holds(root, event)):
                raise
            verdict = ("deny", f"the guard could not check this command ({type(exc).__name__}); write it plainly, or in a file it can read")
        return _decide(stdout, *verdict, root, event)
    targets = _edit_targets(tool_name, tool_input, event)
    if targets is None:
        return _decide(stdout, "deny", UNREAD_PATCH, None, event)
    if not targets:
        return _decide(stdout, "allow", "", None, event)
    paths = [r for t in targets for r in path_location.readings(Path(t) if os.path.isabs(t) else cwd / t)]
    for reading in paths:
        denial = _edit_denial(reading, cwd, event)
        if denial is not None:
            return _decide(stdout, "deny", denial[0], denial[1], event)
    note = _edit_steer(paths[0], event) if dialects.of(event).adds_tool_context else None
    if note:
        # Context for the agent only, with no permissionDecision: the person's own permission settings still decide.
        json.dump({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": note}}, stdout)
    return _decide(stdout, "allow", "", None, event)


UNREAD_PATCH = write_targets.UNREAD_PATCH


def _edit_targets(tool_name: str, tool_input: dict, event: dict) -> list[str] | None:
    """The files an edit tool writes: the one it names, or each file a patch names (`apply_patch`). None for a patch
    that names none the guard can read (an empty one too: its text may sit under a key the guard does not know), since
    the harness's own parser might still find a file in it."""
    if tool_name != dialects.APPLY_PATCH:
        target = repo_config.edit_path(event)
        return [target] if target else []
    patch = str(tool_input.get("command") or "")
    targets = write_targets.apply_patch_targets(patch)
    return targets or None


def _edit_denial(path: Path, cwd: Path, event: dict) -> tuple[str, str | None] | None:
    """(why, the repository to log in) when an edit tool's write to `path` is denied; None when it is allowed."""
    place = path_location.locate(path)
    top, rel = place.top, place.rel
    if not top:
        failed = path_location.git_failed_reason(place.probe, place.why)
        if failed:
            return failed
        # Outside every repository: only a hard link into one is the guard's business.
        link = delegation.hard_link_check(path, [], event, cwd)
        return (link[1], None) if link else None
    if repo_config.is_adopted(top) and any(part.casefold() == ".git" for part in Path(rel).parts):
        return (
            f"{rel} is inside the git directory: an edit tool never writes there, only git and aidd commands do. Run the git or aidd command that changes it",
            top,
        )
    decision, reason = edit_check.check_agent_edit(top, rel, event)
    if decision != "allow":
        return reason, top
    cfg = repo_config.load_config(top) if repo_config.is_adopted(top) else None
    if cfg is None or not workitems.edits_held(cfg, top):
        return None  # check_edit already allowed: for want of a valid config (the gate reports it), or edits are free here
    lead = delegation.delegate_check(top, rel, event, cfg) or delegation.hard_link_check(path, [top], event, cwd)
    return (lead[1], top) if lead is not None else None


def _edit_steer(path: Path, event: dict) -> str | None:
    """`delegate`'s note for an allowed edit of `path`, or None."""
    place = path_location.locate(path)
    cfg = repo_config.load_config(place.top) if place.top and repo_config.is_adopted(place.top) else None
    if cfg is None:
        return None
    try:
        return delegation.delegate_steer(place.top, place.rel, event, cfg)
    except Exception:  # noqa: BLE001  # a steer is a courtesy: it never turns an allow into a failure
        return None
