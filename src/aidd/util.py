"""Small helpers shared by the verifier, the adapters, and the CLI."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shlex
import signal
import subprocess

from . import globs, resources

TRAILER = re.compile(r"^Assisted-by:[ \t]*(\S.*)$", re.M | re.I)
COAUTHOR = re.compile(r"^Co-authored-by:[ \t]*([^<\n]*?)[ \t]*<([^>\n]*)>[ \t]*$", re.M | re.I)

# Credentials stripped from test commands and policy runs.
SECRET_ENV = (
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "AIDD_GATE_TOKEN",
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


# The sort key for a missing timestamp: sorts first, never raises.
EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)


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
    command: list[str], *, timeout: float, cwd: str | None = None, env: dict[str, str] | None = None, capture: bool = True
) -> tuple[int | None, str, str]:
    """(exit code, stdout, stderr) of a command, or (None, ...) when it timed out.

    The command runs in its own process group (a new session on POSIX), and a timeout kills the whole group, so a
    child it spawned cannot outlive it; the process is always reaped. Output is decoded as UTF-8 with invalid bytes
    replaced: a command's bad bytes are its problem, never a crash. OSError (not found, not executable) propagates.
    """
    pipe = subprocess.PIPE if capture else None
    proc = subprocess.Popen(command, cwd=cwd, env=env, stdout=pipe, stderr=pipe, stdin=subprocess.DEVNULL, start_new_session=hasattr(os, "killpg"))
    try:
        out, err = proc.communicate(timeout=timeout)
        code: int | None = proc.returncode
        kill_group(proc)  # hygiene: a background child it left behind does not outlive it
    except subprocess.TimeoutExpired:
        kill_group(proc)
        out, err = proc.communicate()
        code = None
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    return code, (out or b"").decode("utf-8", errors="replace"), (err or b"").decode("utf-8", errors="replace")


def utc_stamp() -> str:
    """Now, in UTC, to the second: `2026-09-28T10:00:00Z`."""
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def toml_list(values: list[str]) -> str:
    """A TOML array of strings (JSON string escapes are valid TOML basic strings)."""
    return "[" + ", ".join(json.dumps(v) for v in values) + "]"


def md_cell(text: object, newline: str = " ") -> str:
    """Text safe inside one Markdown table cell: pipes escaped, newlines replaced with `newline`."""
    return str(text or "").replace("|", "\\|").replace("\n", newline)


def require_env(name: str, where: str) -> str:
    """The value of an environment variable a CI adapter needs; RuntimeError naming `where` when it is unset."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{where}; {name} is not set")
    return value


def norm(identity: str) -> str:
    s = identity.strip().lower()
    return s[1:] if s.startswith("@") else s


# `<tenant>:<identity>`: an identity qualified with its tenant. `email:` and `agent:` are identity kinds, never tenants.
_TENANT_QUALIFIED = re.compile(r"^([a-z0-9][a-z0-9-]{1,62}):(\S+)$")
_IDENTITY_KINDS = ("email", "agent")


def split_tenant(identity: str) -> tuple[str | None, str]:
    """(tenant, the identity without it), normalized: `acme:@alice` is ("acme", "alice"); `alice` and `email:a@b.c` have no tenant."""
    s = norm(identity)
    m = _TENANT_QUALIFIED.match(s)
    if not m or m.group(1) in _IDENTITY_KINDS:
        return None, s
    return m.group(1), norm(m.group(2))


def scoped(identity: str, tenant: str | None) -> str | None:
    """An identity as the config of `tenant` names it: without its own tenant's prefix, or None when it belongs to
    another tenant. Without a tenant nothing is scoped: a qualified identity keeps its prefix and matches only itself."""
    if not tenant:
        return norm(identity)
    owner, rest = split_tenant(identity)
    if owner is None or owner == tenant:
        return rest
    return None


def parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        t = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.UTC)


def red_ok(result: dict) -> bool:
    """A red run proves new behavior only when it failed with a real exit code: not a timeout, not a missing command."""
    return result.get("status") == "failed" and result.get("exit") not in (None, 126, 127)


def is_agent(identity: str, bots: set[str] | None = None) -> bool:
    """True when an identity is a bot account or matches a known AI agent name."""
    s = norm(identity)
    if not s:
        return False
    from . import config as cfgmod

    if cfgmod.is_bot(s):
        return True
    if bots and s in {norm(b) for b in bots}:
        return True
    known = resources.baseline().get("agent_coauthors", {})
    names = [n.lower() for n in known.get("names", [])]
    for n in names:
        if re.search(rf"(?<![a-z0-9_-]){re.escape(n)}(?![a-z0-9_-])", s):
            return True
    return False


def extract_trailers(message: str, pattern: re.Pattern = TRAILER) -> list[str]:
    """Extract trailers from the trailer block (after the last blank line of the message)."""
    norm_msg = (message or "").replace("\r\n", "\n").rstrip()
    if "\n\n" not in norm_msg:
        lines = [line.strip() for line in norm_msg.splitlines() if line.strip()]
        if lines and all(pattern.match(line) or COAUTHOR.match(line) or ":" in line for line in lines):
            return pattern.findall(norm_msg)
        return []
    block = norm_msg.rsplit("\n\n", 1)[1]
    return pattern.findall(block)


_NOREPLY = re.compile(r"^(?:\d+\+)?([a-z0-9](?:[a-z0-9-]{0,38}))@users\.noreply\.github\.com$")


def human_coauthors(message: str, bots: set[str] | None = None) -> set[str]:
    """The people a commit's `Co-authored-by:` trailers name, as author identities.

    A co-author wrote part of the change, so they may not approve it. A GitHub no-reply
    address maps to its login; any other address stays `email:<address>`, which the gate
    treats like an unlinked commit author. Trailers that name an AI agent are left out.
    """
    agents = set(agent_coauthors(message, bots))
    out: set[str] = set()
    for m in COAUTHOR.finditer(message):
        name, email = m.group(1).strip(), m.group(2).strip().lower()
        if (f"{name} <{email}>" if name else email) in agents or not email:
            continue
        login = _NOREPLY.match(email)
        out.add(login.group(1) if login else f"email:{email}")
    return out


def agent_coauthors(message: str, bots: set[str] | None = None) -> list[str]:
    """The `Co-authored-by:` trailers of a commit message that name an AI agent.

    An agent is recognised by its e-mail (the baseline's `agent_coauthors`, or `email:<address>` in
    `identities.bots`) or by a name that carries a known agent name as a whole word.
    """
    known = resources.baseline().get("agent_coauthors", {})
    emails = {e.lower() for e in known.get("emails", [])}
    patterns = [p.lower() for p in known.get("email_patterns", [])]
    names = [n.lower() for n in known.get("names", [])]
    bot_ids = {norm(b) for b in (bots or set())}
    out: list[str] = []
    for m in COAUTHOR.finditer(message):
        name, email = m.group(1).strip(), m.group(2).strip().lower()
        agent = email in emails or f"email:{email}" in bot_ids or any(globs.match(p, email, fold_case=True) for p in patterns)
        agent = agent or any(re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", name.lower()) for n in names)
        if agent:
            out.append(f"{name} <{email}>" if name else email)
    return out
