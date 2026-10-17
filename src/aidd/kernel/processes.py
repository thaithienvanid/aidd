"""Child processes: split a command line, scrub credentials from an environment, and run a command with bounded
output and a timeout that kills its whole process group."""

from __future__ import annotations

import os
import re
import shlex
import signal
import subprocess
import threading
import time

# Credentials stripped from test commands and policy runs.
SECRET_ENV = (
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "AIDD_GITLAB_TOKEN",
    "CI_JOB_TOKEN",
    "ACTIONS_RUNTIME_TOKEN",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
)


def split_command(line: str, windows: bool | None = None) -> list[str]:
    """A command line the operator typed (`--cmd`, `--test`) as argv. Quotes group words on every OS; a backslash
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


def run_bounded(
    command: list[str], *, timeout_seconds: float, cwd: str | None = None, env: dict[str, str] | None = None, capture: bool = True
) -> tuple[int | None, str, str]:
    """(exit code, stdout, stderr) of a command, or (None, ...) when it timed out.

    The command runs in its own process group (a new session on POSIX), and a timeout kills the whole group, so a
    child it spawned cannot outlive it; the process is always reaped. Output is decoded as UTF-8 with invalid bytes
    replaced: a command's bad bytes are its problem, never a crash. OSError (not found, not executable) propagates.
    """
    pipe = subprocess.PIPE if capture else None
    proc = subprocess.Popen(command, cwd=cwd, env=env, stdout=pipe, stderr=pipe, stdin=subprocess.DEVNULL, start_new_session=hasattr(os, "killpg"))
    readers = [_Drain(stream) for stream in (proc.stdout, proc.stderr)] if capture else []
    code: int | None = None
    try:
        exited = wait_unreaped(proc, timeout_seconds)
        # Signal the group while the leader is unreaped (a zombie at most), so its id cannot have been recycled: on
        # exit this is hygiene (a background child it left behind does not outlive it); on a timeout, the kill.
        kill_group(proc)
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
    if exited:
        code = proc.returncode
    out, err = (r.result() for r in readers) if readers else (b"", b"")
    return code, out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")


class _Drain:
    """Reads a pipe to its end on a thread, so a command that writes more than a pipe buffer never blocks."""

    def __init__(self, stream) -> None:
        self.chunks: list[bytes] = []
        self.stream = stream
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self) -> None:
        try:
            for chunk in iter(lambda: self.stream.read(65536), b""):
                self.chunks.append(chunk)
        except (OSError, ValueError):
            pass

    def result(self, grace: float = 5.0) -> bytes:
        # The group is dead, so the pipe is at its end, unless a process left the group (setsid) and holds it open.
        self.thread.join(grace)
        try:
            self.stream.close()
        except OSError:
            pass
        return b"".join(self.chunks)


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


def require_env(name: str, where: str) -> str:
    """The value of an environment variable a CI adapter needs; RuntimeError naming `where` when it is unset."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{where}; {name} is not set")
    return value
