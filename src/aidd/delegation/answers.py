"""The delegate's side of a standing delegation: the packet it reads, the answer it gives, the stop, and the hook that
answers Claude Code's prompt only for a verified answer.

The delegate reads the packet the check builds, never the asker's summary: the check's output, the diffstat, the parts of
the Spec an accept covers, the person's saved request when the default branch holds one, and the commit subjects, each
quoted as data and held whole (a text that would not fit is a deferral, never a cut). Its answer counts only after the
check passes again, and the hook runs the check once more, on the exact command, before it lets the command run.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from aidd import config, records
from aidd.delegation import commands, outcome, parts, policy
from aidd.delegation.check import Check, Request
from aidd.kernel import documents, git, regular_files, timestamps

MAX_REASON_CHARS = 200


def _texts(check: Check) -> dict[str, dict]:
    """Every text the delegate reads, each as data, whole: the check defers on a text that would not fit (text_checks.fit),
    so a cut text never stands behind an accept. The Spec's own Request says who wrote it."""
    out: dict[str, dict] = {}
    try:
        read = parts.read(check)
    except documents.DocumentError:
        return out  # the check has deferred on the Spec (text_checks.guard)
    for name, text in read.items():
        out[name] = parts.quoted(text, parts.caps()[name])
        if source := parts.source_of(check, name):
            out[name]["source"] = source
    return out


def packet(request: Request) -> dict:
    """What the delegate reads: the check, recomputed, then the diffstat and the texts as quoted data. It carries no diff
    body and nothing the asker wrote but what the Spec and the commits say, and the check tells the delegate which is which."""
    check = outcome.evaluate(request)
    result = outcome.outcome(check)
    outcome.record_check(check, result)
    try:
        diffstat = parts.diffstat(check)
    except git.GitError:
        diffstat = []  # the check has deferred on it (text_checks.fit)
    return {
        "schema_version": "1",
        "check": result,
        "diffstat": diffstat[: parts.max_diffstat_files()],
        "quoted": _texts(check),
        "answer": "Call delegate_answer with outcome accept or defer, the action, the command, the head, and a reason of one line. "
        "Accept only on an eligible check; defer for any doubt, such as drift from the person's request.",
    }


def answer(request: Request, said: str, reason: str) -> dict:
    """Record the delegate's answer after the check passes again. An accept on a check that now defers is no answer: the
    ask goes to the person, with no record that would hold the tree. A defer is recorded, and is final for the tree."""
    check = outcome.evaluate(request)
    result = outcome.outcome(check)
    outcome.record_check(check, result)
    if said not in ("accept", "defer"):
        raise ValueError("outcome is accept or defer")
    if said == "accept" and result["outcome"] != "eligible":
        return {"outcome": "defer", "recorded": None, "reasons": result["reasons"], "next": result["next"]}
    data = {
        "action": result["action"],
        "covers": {k: result["covers"][k] for k in outcome.COVERS if result["covers"].get(k)},
        "outcome": said,
        "reason": documents.one_line(reason or "no reason given", MAX_REASON_CHARS),
        "check": result.get("record") or "00000000T000000000Z-00000000",
        "delegation_commit": check.tip or "0" * 40,
    }
    with records.written_by_delegation():
        record, _ = records.add_record("delegate_answer", data, by=config.DECIDED_BY, subject=result["covers"].get("spec"), cwd=check.top)
    out = {"outcome": said, "recorded": record["id"], "covers": data["covers"]}
    if said == "accept":
        out |= {
            "trailers": result["trailers"],
            "next": {"what": "The lead runs the exact command in covers, or, for a Spec, commits the approval with the trailers."},
        }
    else:
        out["next"] = {"what": "Ask the person, with the delegate's reason."}
    return out


def stop(cwd: str = ".") -> Path:
    """Turn the delegation off in this clone: the stop file, which only narrows. A person deletes it to turn it back on."""
    common = Path(git.common_dir(cwd))
    path = common.joinpath(*policy.STOP_FILE)
    regular_files.write_safely(common, path, f"stopped at {timestamps.utc_stamp()}\n")  # never through a link
    return path


def asked(command: str) -> tuple[str, str] | None:
    """The delegable action a command's exact template gives, and the head it names, or None: a record never says it."""
    for action in policy.delegable():
        shape = policy.template(action)
        values = commands.fit(shape, command)[0] if shape else None
        if values and values.get("sha"):
            return action, values["sha"]
    return None


def accepted_here(cwd: str, action: str, command: str, head: str) -> bool:
    """Whether the delegate accepted this exact command on this exact head, in a record this clone wrote under the
    delegate's own name: a pulled record is another's text, so it never counts."""
    for rec in records.delegate_answers(cwd):
        data = rec.get("data") or {}
        covers = data.get("covers") or {}
        if data.get("action") == action and data.get("outcome") == "accept" and covers.get("command") == command and covers.get("head") == head:
            return True
    return False


def _allow(event: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": event, "decision": {"behavior": "allow"}}}


def hook(event: dict, env: dict[str, str]) -> dict | None:
    """Claude Code's PermissionRequest or PreToolUse hook. PreToolUse denies the delegate's tools to any other agent.
    PermissionRequest allows them to the delegate, and allows a delegated command only when the delegate accepted that
    exact command and head here, and the check, run again now on them, is eligible. Anything else is no decision, so the prompt stays, or a headless run
    denies the call. A record is a precondition, never the reason: a forged accept skips only the delegate's judgment, a
    pulled one counts for nothing, and the delegate's defer reaches the hook through the check, final for the tree."""
    name, tool, agent = event.get("hook_event_name"), event.get("tool_name"), event.get("agent_type")
    if tool in policy.DELEGATE_TOOLS:
        if name == "PreToolUse" and agent != config.DELEGATE_AGENT:
            reason = "only aidd-team:delegate answers a delegated ask; ask the delegate, or ask the person"
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}
        return _allow("PermissionRequest") if name == "PermissionRequest" and agent == config.DELEGATE_AGENT else None
    if name != "PermissionRequest" or tool != "Bash":
        return None
    command = str((event.get("tool_input") or {}).get("command") or "")
    cwd = str(event.get("cwd") or env.get("CLAUDE_PROJECT_DIR") or ".")
    found = asked(command) if command and git.repository_top(cwd) else None
    if not found or not accepted_here(cwd, found[0], command, found[1]):
        return None
    # The delegate's accept is a precondition; the check, run now on the exact command and head, is the reason to allow,
    # and it reads the delegate's defer on this tree as final. It writes this run's record.
    result = outcome.run_check(Request(action=found[0], command=command, head=found[1], cwd=cwd, env={**env, "CLAUDECODE": "1"}))
    if result["outcome"] == "eligible" and result["covers"].get("command") == command:
        return _allow("PermissionRequest")
    why = "; ".join(f"{r['code']}: {documents.one_line(r['detail'], 200)}" for r in result["reasons"][:3])
    print(
        f"aidd delegate hook: no decision, so the prompt stays ({why or 'the command is not the one the delegate accepted'}). {result['next']['what']}",
        file=sys.stderr,
    )
    return None


def hook_main(stdin_text: str, env: dict[str, str] | None = None) -> str:
    """`aidd delegate hook`: the hook's answer as Claude Code reads it, or "" for no decision. Any failure is no decision."""
    try:
        event = json.loads(stdin_text)
        answer_ = hook(event, dict(os.environ if env is None else env)) if isinstance(event, dict) else None
    except Exception as exc:  # noqa: BLE001  # a hook that fails gives no decision, so the prompt or the denial stays
        print(
            f"aidd delegate hook: no decision, so the prompt stays ({type(exc).__name__}: {documents.one_line(str(exc), 200)}). Run `aidd doctor`.",
            file=sys.stderr,
        )
        return ""
    return json.dumps(answer_) if answer_ else ""
