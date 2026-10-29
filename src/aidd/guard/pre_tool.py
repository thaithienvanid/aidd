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
    browser_pages,
    command_check,
    delegation,
    denial_log,
    dialects,
    edit_check,
    hook_capture,
    mcp_tools,
    path_location,
    pending_notes,
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
        # A git the session's PATH or GIT_* names never answers for the guard; one call reads the repository once.
        with git.system_only(), git.memo(), _deadline(deadline_seconds):
            raw = stdin.read()
            hook_capture.keep("pre-tool", raw)  # under AIDD_HOOK_CAPTURE only
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


# How many of a call's text values `_reaches_adopted_repo` reads before it takes the call as reaching one.
MAX_NAMED_VALUES = 64


def _reaches_adopted_repo(tool_input: object, cwd: Path) -> bool:
    """Whether any text in a tool call's input, read as a path from `cwd`, lies in a repository that adopted aidd. An
    input too large to read through, or a value that cannot be read as a path, counts as one that does (fail closed)."""
    values: list[str] = []
    stack = [tool_input]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            values.append(item)
        elif isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
        if len(values) > MAX_NAMED_VALUES:
            return True
    for value in values:
        if not value.strip() or "\n" in value:
            continue  # no path: empty, or prose and code over several lines
        try:
            place = path_location.locate(cwd / Path(value).expanduser())
        except (OSError, ValueError, RuntimeError):
            return True
        if place.top and repo_config.is_adopted(place.top):
            return True
    return False


def _decide(stdout, decision: str, reason: str, root: str | None = None, event: dict | None = None) -> int:
    """Answer the harness that sent `event`; a deny is logged in `root` first, with any line the prompt hook could not
    show joined to its reason (pending_notes.py)."""
    if decision == "allow":
        return _allow(stdout, event)
    if event is not None and (pending := _pending(event, root)):
        reason = f"{reason}\n\nAlso: {pending}"
    if root and event is not None:
        try:
            denial_log.log_denial(root, event, reason)
        except Exception:  # noqa: BLE001  # the log is a convenience: it must never turn a deny into an allow
            pass
    return _answer(stdout, dialects.of(event), decision, reason)


def _allow(stdout, event: dict | None, note: str | None = None) -> int:
    """An allow, with `note` for the agent and any line the prompt hook could not show, as context with no
    permissionDecision: the person's own permission settings still decide."""
    pending = _pending(event, None) if event is not None else None
    note = "\n\n".join(n for n in (pending, note) if n) or None
    if note:
        json.dump({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": note}}, stdout)
        return 0
    return _answer(stdout, dialects.of(event), "allow", "", event)


def _pending(event: dict, root: str | None) -> str | None:
    """The line the prompt hook kept for this session, where the harness does not show the prompt hook's own."""
    if dialects.of(event).shows_prompt_note:
        return None
    try:
        place = root or _repo_of(event)
        return pending_notes.take(place, event.get("session_id")) if place else None
    except Exception:  # noqa: BLE001  # a note is a courtesy: it never changes a decision, nor fails one
        return None


def _repo_of(event: dict) -> str | None:
    """The repository the event's working folder is in, for a hook answer that names none."""
    cwd = event.get("cwd")
    return git.toplevel(cwd) if isinstance(cwd, str) and cwd else None


def _answer(stdout, dialect: dialects.Dialect, decision: str, reason: str, event: dict | None = None) -> int:
    """The decision in `dialect`'s format: a deny with its reason, or an allow as the harness's "no opinion" for the
    call in `event`, which leaves it to the person's permission settings."""
    answer = dialect.no_opinion(event) if decision == "allow" else dialect.decision(decision, reason)
    if answer is not None:
        json.dump(answer, stdout)
    return 0


def _normalized(event: object) -> dict:
    """The hook event in the guard's fields (`dialects`); TypeError when it is not a JSON object."""
    if not isinstance(event, dict):
        raise TypeError("the hook event is not a JSON object")
    return dialects.of(event).normalize(event)


def _helper(root: str | None, event: dict) -> bool:
    """Whether `event` is a helper that only reads (role_areas.is_read_only_subagent), by the config in `root`."""
    return role_areas.is_read_only_subagent(event, repo_config.load_config(root) if root else None)


def _start_denial(cwd: Path, event: dict, tool_input: dict) -> tuple[str, str | None] | None:
    """(reason, root) when the agent may not start the subagent it names (role_areas.start_denial). Only an adopted
    repository whose edits the loop does not hold (advisory mode, an explore branch) lets it: a config the guard cannot
    read holds them, and so does a workspace outside any adopted repository, since a role exists only with aidd."""
    top, _ = path_location.repo_top(cwd)
    root = top if top and repo_config.is_adopted(top) else None
    cfg = repo_config.load_config(root) if root else None
    if cfg is not None and not workitems.edits_held(cfg, root):  # type: ignore[arg-type]
        return None
    kind = tool_input.get("subagent_type")
    if kind is not None and not isinstance(kind, str):  # a type the guard cannot read could start any agent
        return dialects.AMBIGUOUS_CALL, root
    reason = role_areas.start_denial(event, kind or "", cfg, unheld=tool_input.get("unheld") is True)
    return (reason, root) if reason else None


def _pre_tool(raw: str, stdout) -> int:
    try:
        loaded = json.loads(raw)
    except ValueError:
        return _broke(stdout, raw, "the guard could not read the tool call")
    event = _normalized(loaded)
    cwd = Path(event.get("cwd") or ".")
    tool_name, tool_input = str(event.get("tool_name") or ""), event.get("tool_input") or {}
    if event.get("opaque_tool"):
        # Code Mode runs the tools it calls itself, so the guard would never see them; a shell call may name its command
        # in a form the guard cannot read; and a harness's tool the guard does not know may write anything. Deny rather
        # than trust any of them, and name what to do instead (`dialects._OPENCODE_OPAQUE`, `dialects.OPAQUE_SHELL`,
        # `dialects.unknown_tool`). Only an unknown tool of a session outside every adopted repository, that names no
        # path inside one, is left alone: aidd does nothing there.
        top, _ = path_location.repo_top(cwd)
        root = top if top and repo_config.is_adopted(top) else None  # where the deny is logged
        if event.get("unknown_tool") and root is None and not _reaches_adopted_repo(tool_input, cwd):
            return _allow(stdout, event)  # a tool of a session outside aidd that names nothing inside it
        reason = event["opaque_tool"] if isinstance(event["opaque_tool"], str) else CODE_MODE
        return _decide(stdout, "deny", reason, root, event)
    if tool_name in dialects.SUBAGENT_STARTS and (denied := _start_denial(cwd, event, tool_input)):
        return _decide(stdout, "deny", denied[0], denied[1], event)
    if tool_name.startswith("mcp__") or tool_name in denial_log.SHELL_TOOLS:  # PowerShell commands get the same checks as Bash
        top, why = path_location.repo_top(cwd)
        failed = None if top else path_location.git_failed_reason(cwd, why)
        if failed:
            return _decide(stdout, "deny", failed[0], failed[1], event)
        # The session's own repository, when it adopted aidd. Outside one, only the writes are checked: each in the
        # repository that holds its target.
        root = top if top and repo_config.is_adopted(top) else None
        if tool_name.startswith("mcp__"):
            decision, reason, note = _mcp_verdict(root, cwd, tool_name, tool_input, event)
            return _allow(stdout, event, note) if decision == "allow" and note else _decide(stdout, decision, reason, root, event)
        command = tool_input.get("command") or ""
        if not command:
            return _decide(stdout, "allow", "", root, event)
        try:
            verdict = command_check.check_command(root, str(cwd), command, event)
        except Exception as exc:  # a parse that breaks never turns into an allow for a writer the guard holds
            if not (role_areas.role_of(event) or _helper(root, event) or delegation.holds(root, event)):
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
    note = _advice(paths[0], event) or _edit_steer(paths[0], event) if dialects.of(event).adds_tool_context else None
    return _allow(stdout, event, note)


def _mcp_verdict(root: str | None, cwd: Path, tool_name: str, tool_input: dict, event: dict) -> tuple[str, str, str | None]:
    """allow or deny, why, and a note for the agent, for an MCP tool call in the session's repository `root` (None outside
    one that adopted aidd). The note is for a browser call that goes through, and says what it would be denied for."""
    # Claude Code's MCP dialog is known to ask the person. Only an event that names itself one counts: Claude Code
    # is the fallback dialect, so an event no dialect claims is never taken for it.
    asks = dialects.of(event) is dialects.CLAUDE_CODE and isinstance(event.get("permission_mode"), str) and "transcript_path" in event
    decision, reason = mcp_tools.check_mcp_tool(tool_name, tool_input, dialogs_ask=asks) if root else ("allow", "not an aidd repository")
    note = None
    if decision == "allow" and root and browser_pages.is_browser_tool(tool_name):
        # A browser opens only local pages, and the hosts the config lists; a config the guard cannot read lists none.
        cfg = repo_config.load_config(root)
        if found := browser_pages.refusal(tool_name, tool_input, browser_pages.listed_hosts(cfg)):
            held, note = _browser_hold(cfg, root, event, found[0])
            if held:
                return "deny", found[0], None
            if note and not _first_mention(root, event, "browser " + found[1]):
                note = None  # said once for each host in a session, not on every call
    if decision == "allow":
        decision, reason = delegation.delegate_mcp(root, str(cwd), tool_name, tool_input, event) or (decision, reason)
    return decision, reason, note


def _first_mention(root: str, event: dict, key: str) -> bool:
    """Whether this is the session's first note for `key` (the marker `_advice` keeps); true when the store cannot say."""
    from aidd import autopilot

    sid = event.get("session_id")
    if not (isinstance(sid, str) and autopilot.SESSION_ID.match(sid)):
        return True
    try:
        return autopilot.claim_first_mention(root, sid, key)
    except (autopilot.LeaseError, OSError):
        return True  # say it rather than never


def _browser_hold(cfg, root: str, event: dict, why: str) -> tuple[bool, str | None]:
    """(whether the browser call `why` names is denied, else the note for the agent). It binds by who acts: a role or a
    helper (a subagent, or a lead under an autopilot lease or playing a role: `delegation.acts_alone`) follows the mode, denying in enforce and noting in advisory;
    the lead, the person's own session (not one that runs autopilot or plays a role), is denied only under the audited profile, and otherwise told. A free worktree (an
    explore branch, the loop switched off) holds nothing. A note goes only where the harness takes tool context."""
    mode = workitems.guard_mode(cfg, root)
    if mode == "free":
        return False, None
    works_alone = delegation.acts_alone(root, event)
    if mode == "enforce" and (works_alone or cfg is None or cfg.profile == "audited"):
        return True, None  # a config the guard cannot read holds, like the other rules
    if not dialects.of(event).adds_tool_context:
        return False, None
    if mode == "advise":
        return False, f"aidd (advisory mode, so this goes through): {why}"
    return False, f"aidd (this is your own session, so this goes through; a role or a helper would be denied here): {why}"


UNREAD_PATCH = write_targets.UNREAD_PATCH
# OpenCode's Code Mode tool (`dialects.OpenCode` marks it): the code it runs calls the tools itself, so the guard cannot
# read what it will write or run. The reason names the calls to make directly, which the guard does check.
CODE_MODE = "this tool runs code the guard cannot read inside: call the tools directly instead (read, shell, write, edit)"


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
    if record := delegation.harness_record(path):
        return record, None
    place = path_location.locate(path)
    top, rel = place.top, place.rel
    session_top = path_location.repo_top(cwd)[0]
    if path_location.in_git_dir(path, [session_top, top]):
        return (
            f"{path} is inside the git directory: an edit tool never writes there, only git and aidd commands do. Run the git or aidd command that changes it",
            top or session_top,
        )
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


def _advice(path: Path, event: dict) -> str | None:
    """In advisory mode, a note on what enforce mode would have stopped: the edit goes through, and the agent knows."""
    place = path_location.locate(path)
    if not place.top or not repo_config.is_adopted(place.top):
        return None
    why = edit_check.advisory_note(place.top, place.rel, event)
    if not why:
        return None
    # One note for each kind of thing in a session, not one for each edit: a person in a hurry is never nagged.
    from aidd import autopilot

    sid = event.get("session_id")
    if isinstance(sid, str) and autopilot.SESSION_ID.match(sid):
        try:
            if not autopilot.claim_first_mention(place.top, sid, "advise " + why.replace(place.rel, "<path>")):
                return None
            why += " This note comes once a session; later edits like it go through without one."
        except (autopilot.LeaseError, OSError):
            pass  # the store cannot be read: say it every time rather than never
    return f"aidd (advisory mode, so this goes through): {why}"


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
