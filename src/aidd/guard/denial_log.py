"""The guard log: one JSON line per deny, with its stable reason code, and every secret-looking value redacted."""

from __future__ import annotations

import hashlib
import json
import os
import re

from aidd import config
from aidd.guard import repo_config, role_areas
from aidd.kernel.timestamps import utc_stamp

# Each deny reason's code, for the denial log and `aidd metrics --guard`: the first entry whose text the reason
# contains names it. The texts are the fixed parts of the reasons above; a new deny reason needs a row here.
REASON_CODES: tuple[tuple[str, str], ...] = (
    ("the aidd config is invalid", "config_invalid"),
    ("autopilot for another session", "autopilot_session"),
    ("runs code the guard cannot read", "shell_opaque"),
    ("hard links, so a write to it changes", "hard_link"),
    ("inside the git directory", "git_dir"),
    ("agents.delegate", "delegate"),
    ("may only read (the loop contract's helper rule", "subagent_read_only"),
    ("types an approval", "decision_typed"),
    ("that the guard does not allow there", "device_command"),
    ("denies what it cannot check", "shell_unparsed"),
    ("the guard could not", "guard_failed"),
    ("unknown aidd-team role", "unknown_role"),
    # Before the decisions it names: a shell write to a decision file is unreadable, whichever decision it holds.
    ("which only a person records; use the Edit or Write tool", "decision_unreadable"),
    ("go_no_go, sign_off, or outcome, which only a person records", "proposal_decision"),
    ("an Initiative's go_no_go, which only a person records", "initiative_decision"),
    ("of a proposal; ", "proposal_part"),
    ("an exploration's outcome, which only a person records", "exploration_decision"),
    ("only a person adds a dismissal", "review_dismissal"),
    ("against the held commands", "guard_failed"),
    ("is a held command", "held_command"),
    ("carries `/aidd approve`", "approval_post"),
    ("where local approvals are recorded", "decision_record"),
    ("agents never approve or merge", "approve_or_merge"),
    ("an agent never runs it; the person decides", "approve_or_merge"),
    ("an agent never approves;", "approve_or_merge"),
    ("agents never approve;", "approve_or_merge"),
    ("agents never merge;", "approve_or_merge"),
    ("agents never decide for a person", "proposal_decision"),
    ("changes commit signing", "signing_config"),
    ("lands work on the base branch", "base_branch"),
    ("protected branch", "protected_branch"),
    ("reaches the protected branches", "protected_branch"),
    ("the shell check does not expand it", "shell_unknown_target"),
    ("so its target files are unknown", "shell_unknown_target"),
    ("cannot read the patch", "shell_unknown_target"),
    ("is a protected path", "protected_path"),
    ("frozen by Spec approval", "frozen_file"),
    ("writes it while specifying, and after Spec approval nobody does", "not_owner"),
    ("outside the area of the", "role_area"),
    ("role is read-only and writes no file", "role_area"),
    ("role writes only", "role_area"),
    ("no active Spec, so", "no_active_spec"),
    ("is outside the scope of", "out_of_scope"),
)
_LOG_FIELD_MAX = 200
# Secret-looking values a logged command may carry; each keeps its name and loses its value.
_SECRETS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"(?i)(authorization\s*[:=]\s*)(?:(bearer|basic|token|bot)\s+)?[^\s'\"]+"), "AUTH"),
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1***"),
    (re.compile(r"(?i)\b([A-Z0-9_.-]*(?:TOKEN|KEY|SECRET|PASSWORD|PASSWD|PWD|CREDENTIALS?)[A-Z0-9_.-]*)=(\"[^\"]*\"|'[^']*'|[^\s'\"]+)"), r"\1=***"),
    (
        re.compile(r"(?i)(--(?:password|passwd|pass|token|api-key|apikey|secret|client-secret|auth-token|access-token)(?:=|\s+))(\"[^\"]*\"|'[^']*'|\S+)"),
        r"\1***",
    ),
    # Any other option whose name says it carries a secret: --aws-secret-access-key X, --private-key=...
    (
        re.compile(r"(?i)(--[a-z0-9-]*(?:password|passwd|token|secret|api-?key|access-key|private-key)[a-z0-9-]*(?:=|\s+))(\"[^\"]*\"|'[^']*'|\S+)"),
        r"\1***",
    ),
    # A header whose name says it carries a secret: X-Api-Key: ..., Private-Token: ..., X-Auth-Token: ...
    (re.compile(r"(?i)(\b(?!authorization\s*:)[a-z0-9-]*(?:api-?key|token|secret|password|auth)[a-z0-9-]*\s*:\s*)[^\s'\"]+"), r"\1***"),
    # curl -u user:password, --user=user:password (the user stays, the password goes)
    (re.compile(r"(?i)((?:^|[\s;|&(])(?:-u|--user|--proxy-user)(?:=|\s*))([\"']?)([^\s:'\"]*):([^\s'\"]+)"), r"\1\2\3:***"),
    # mysql -pSECRET (the password attached to -p)
    (re.compile(r"(?i)(\b(?:mysql\w*|mariadb\w*)\b[^|;&\n]*?\s-p)(?=[^\s-])(\"[^\"]*\"|'[^']*'|[^\s'\"]+)"), r"\1***"),
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^/\s:@'\"]*):[^/\s@'\"]+@"), r"\1:***@"),
    (
        re.compile(
            r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16})"
        ),
        "***",
    ),
)


def redact(text: str) -> str:
    """`text` with every secret-looking value _SECRETS matches replaced by `***`."""
    for pattern, repl in _SECRETS:
        if repl == "AUTH":
            text = pattern.sub(lambda m: m.group(1) + (m.group(2) + " " if m.group(2) else "") + "***", text)
        else:
            text = pattern.sub(repl, text)
    return text


def reason_code(reason: str) -> str:
    """The stable code of a deny reason (REASON_CODES), or "other"."""
    for text, code in REASON_CODES:
        if text in reason:
            return code
    return "other"


def log_denial(root: str, event: dict, reason: str) -> None:
    """Append one JSON line for a deny to the guard log in the git directory (config.guard_log; the guard's docstring
    says what it holds), so every worktree's denials count together; a failure to write is ignored."""
    ti = event.get("tool_input") or {}
    tool = str(event.get("tool_name") or "")
    entry: dict = {
        "ts": utc_stamp(),
        "decision": "deny",
        "role": role_areas.role_of(event),
        "helper": role_areas.is_read_only_subagent(event),
        "tool": tool,
        "reason": reason_code(reason),
    }
    if session := str(event.get("session_id") or "")[:_LOG_FIELD_MAX]:
        entry["session"] = session  # which run a deny came from, so one session's denials read together
    if tool in SHELL_TOOLS:
        command = redact(str(ti.get("command") or ""))
        entry["command"] = command[:_LOG_FIELD_MAX]
        if len(command) > _LOG_FIELD_MAX:
            # Cut for the log's size; its length and hash still tell two long commands apart.
            entry["command_len"] = len(command)
            entry["command_sha256"] = hashlib.sha256(command.encode("utf-8", "replace")).hexdigest()[:16]
    elif not tool.startswith("mcp__"):  # an MCP tool's name says what was denied; its input may hold anything
        target = repo_config.edit_path(event) or ""
        entry["path"] = (repo_config.repo_relative(root, target) if target else "")[:_LOG_FIELD_MAX]
    try:
        log = config.guard_log(root)
        if log.parent.is_symlink() or log.is_symlink():
            return
        log.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Owner-only, as the store's other files are, and never through a link swapped in after the check above.
        fd = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    except (OSError, ValueError):
        pass


SHELL_TOOLS = ("Bash", "PowerShell")
