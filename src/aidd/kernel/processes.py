"""Child processes: split a command line, scrub credentials from an environment, and run a command with bounded
output and a timeout that kills its whole process group."""

from __future__ import annotations

import os
import re
import shlex
import signal
import subprocess
import time

# Credentials stripped from test commands and policy runs. The docs list them in this order.
SECRET_ENV = (
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "AIDD_GITLAB_TOKEN",
    "CI_JOB_TOKEN",
    "ACTIONS_RUNTIME_TOKEN",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
)


_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")


def assignment_problem(argv: list[str]) -> str | None:
    """Why a command vector cannot start: its first word is a shell's `NAME=value`, which aidd runs as the program,
    because it starts a command with no shell. None for any other command."""
    if not argv or not _ASSIGNMENT.match(argv[0]):
        return None
    word, fixed = (_printable(s) for s in (argv[0], shlex.join(["env", *argv])))
    return f"`{word}` is an environment variable, but aidd starts a command with no shell, so it would run `{word}` as the program; start the command with `env`, as in `{fixed}`"


def _printable(text: str) -> str:
    """Text from a file, safe to print: no control character reaches the terminal, and no backtick ends the quote."""
    return "".join(c if c.isprintable() and c != "`" else "?" for c in text)


def split_command(line: str, windows: bool | None = None) -> list[str]:
    """A command line the operator typed (`--agent-command`, `--test`) as argv. Quotes group words on every OS; a backslash
    escapes only off Windows, where it is the path separator (`C:\\Python\\python.exe agent.py`)."""
    if not (os.name == "nt" if windows is None else windows):
        return shlex.split(line)
    lex = shlex.shlex(line, posix=True)
    lex.whitespace_split = True
    lex.commenters = ""
    lex.escape = ""
    return list(lex)


# Names that look like credentials. `aidd observe` drops them unless the operator passes one by name.
CREDENTIAL_NAME = re.compile(r"TOKEN|SECRET|PASSW(OR)?D|PRIVATE_KEY|API_?KEY|ACCESS_KEY|CREDENTIAL|_KEY$", re.I)


def scrub_credentials(env: dict[str, str], keep: list[str] | tuple[str, ...] = ()) -> dict[str, str]:
    """The environment without SECRET_ENV and without any variable whose name looks like a credential, except `keep`."""
    kept = set(keep)
    return {k: v for k, v in env.items() if k not in SECRET_ENV and (k in kept or not CREDENTIAL_NAME.search(k))}


def kill_group(proc: subprocess.Popen) -> None:
    """Kill a process started in its own session and everything in its process group (on POSIX)."""
    if hasattr(os, "killpg"):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    if proc.poll() is None:
        proc.kill()


def wait_unreaped(proc: subprocess.Popen, timeout_seconds: float) -> bool:
    """Wait up to `timeout` seconds for `proc` to exit without reaping it; True when it exited.

    While the leader is unreaped its process id, and so its process group's id, cannot be reused, so `kill_group`
    after this signals the right group. Where the platform cannot wait without reaping, it waits and reaps.
    """
    if not (hasattr(os, "waitid") and hasattr(os, "WNOWAIT")):
        try:
            proc.wait(timeout=timeout_seconds)
            return True
        except subprocess.TimeoutExpired:
            return False
    deadline = time.monotonic() + timeout_seconds
    delay = 0.001
    while True:
        try:
            if os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None:
                return True
        except ChildProcessError:
            return True  # already reaped
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(delay, remaining))
        delay = min(delay * 2, 0.05)
