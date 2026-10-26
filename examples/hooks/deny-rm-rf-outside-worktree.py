#!/usr/bin/env python3
"""A team's own Claude Code PreToolUse rule, next to aidd's guard: deny `rm -rf` on a path outside this worktree.

Claude Code runs every matching PreToolUse hook in parallel and the most restrictive answer wins (deny, then ask,
then allow), so this hook only ever adds a deny; aidd's guard still decides everything it checks. The script reads
the event JSON on stdin and prints the documented answer, or nothing to let the call through
(code.claude.com/docs/en/hooks, checked 2026-09-28). Python 3.9+ standard library only.

It is a best-effort rule, not a sandbox: a command built at run time (`sh -c "$X"`, `find -delete`, a script that
removes files) gets past it. Keep the real limits in the operating system or a container.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys

SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", ";;", "|&"}
PREFIXES = {"sudo", "command", "builtin", "env", "nice", "nohup", "time", "xargs"}


def worktree(cwd: str) -> str:
    """The top of the git worktree the session works in; the session's directory when it is not in one."""
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return os.path.realpath(cwd)
    return os.path.realpath(out.stdout.strip() or cwd)


def rm_targets(command: str) -> list[list[str]]:
    """The operands of each `rm` in the command that removes recursively and by force."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()")
        lexer.whitespace_split = True
        words = list(lexer)
    except ValueError:  # unbalanced quotes: nothing to judge
        return []
    found: list[list[str]] = []
    i = 0
    while i < len(words):
        start = i == 0 or words[i - 1] in SEPARATORS
        while start and i < len(words) and (words[i] in PREFIXES or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[i])):
            i += 1
        if start and i < len(words) and os.path.basename(words[i]) == "rm":
            recursive = force = False
            operands: list[str] = []
            j, options = i + 1, True
            while j < len(words) and words[j] not in SEPARATORS:
                w = words[j]
                if options and w == "--":
                    options = False
                elif options and w.startswith("--"):
                    recursive |= w == "--recursive"
                    force |= w == "--force"
                elif options and w.startswith("-") and len(w) > 1:
                    recursive |= bool(set(w[1:]) & {"r", "R"})
                    force |= "f" in w[1:]
                else:
                    operands.append(w)
                j += 1
            if recursive and force:
                found.append(operands)
            i = j
        i += 1
    return found


def outside(operand: str, cwd: str, top: str) -> bool:
    """True when the operand names a path outside `top` or the worktree itself, or one this rule cannot judge (it
    holds a variable or a command substitution)."""
    if "$" in operand or "`" in operand:
        return True
    path = os.path.realpath(os.path.join(cwd, os.path.expanduser(operand)))
    return path == top or not path.startswith(top + os.sep)


def decide(event: dict) -> str | None:
    """The reason to deny, or None to leave the call to the other hooks and the permission rules."""
    if event.get("tool_name") != "Bash":
        return None
    command = str((event.get("tool_input") or {}).get("command") or "")
    cwd = str(event.get("cwd") or os.getcwd())
    top = worktree(cwd)
    for operands in rm_targets(command):
        bad = [o for o in operands if outside(o, cwd, top)]
        if bad:
            return f"team rule: rm -rf outside this worktree ({top}) is not allowed: {', '.join(bad)}"
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
        reason = decide(event if isinstance(event, dict) else {})
    except Exception as exc:  # noqa: BLE001  # a broken team rule must not break the session; aidd's guard still runs
        print(f"deny-rm-rf-outside-worktree: skipped ({type(exc).__name__})", file=sys.stderr)
        return 0
    if reason:
        answer = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}
        json.dump(answer, sys.stdout)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
