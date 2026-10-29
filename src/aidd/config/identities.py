"""Identities: who is a person, a bot, or an agent; logins and tenants normalized; the agents a commit's trailers name;
and the operator this machine's git and gh sign in as."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import unicodedata
from collections.abc import Collection
from pathlib import Path

from aidd.config import baseline
from aidd.kernel import globs

BOT_ACCOUNTS = ("web-flow", "github-actions", "ghost")


def is_bot(identity: str) -> bool:
    s = identity.strip().lower().lstrip("@")
    return s.endswith("[bot]") or s in BOT_ACCOUNTS


TRAILER = re.compile(r"^Assisted-by:[ \t]*(\S.*)$", re.M | re.I)


COAUTHOR = re.compile(r"^Co-authored-by:[ \t]*([^<\n]*?)[ \t]*<([^>\n]*)>[ \t]*$", re.M | re.I)


def normalize_identity(identity: str) -> str:
    """An identity as aidd compares it for equality: stripped, lowercased, and without a leading `@`. It never folds
    lookalikes, so a fullwidth or zero-width variant of an allow-listed identity (an Approver, a system account) never
    equals it. Only agent detection folds them (`_detection_key`)."""
    s = identity.strip().lower()
    return s[1:] if s.startswith("@") else s


def _detection_key(identity: str) -> str:
    """An identity as `is_agent` reads it: NFKC-folded (a fullwidth `ａgent` is `agent`), without zero-width and other
    format characters (Unicode category Cf), then normalized. Never an equality key for an allow-list."""
    return normalize_identity("".join(c for c in unicodedata.normalize("NFKC", identity) if unicodedata.category(c) != "Cf"))


def _non_ascii_letters(identity: str) -> bool:
    """True when a letter outside ASCII is left after folding, such as a Cyrillic `а` in `clаude`: a login, an
    `agent:` name, or a known agent's name could hide behind it, so it is read as an agent (fail-closed)."""
    return any(c.isalpha() and not c.isascii() for c in identity)


# `<tenant>:<identity>`: an identity qualified with its tenant. `email:` and `agent:` are identity kinds, never tenants.
_TENANT_QUALIFIED = re.compile(r"^([a-z0-9][a-z0-9-]{1,62}):(\S+)$")


_IDENTITY_KINDS = ("email", "agent")


def split_tenant(identity: str) -> tuple[str | None, str]:
    """(tenant, the identity without it), normalized: `acme:@alice` is ("acme", "alice"); `alice` and `email:a@b.c` have no tenant."""
    s = normalize_identity(identity)
    m = _TENANT_QUALIFIED.match(s)
    if not m or m.group(1) in _IDENTITY_KINDS:
        return None, s
    return m.group(1), normalize_identity(m.group(2))


def scoped(identity: str, tenant: str | None) -> str | None:
    """An identity as the config of `tenant` names it: without its own tenant's prefix, or None when it belongs to
    another tenant. Without a tenant nothing is scoped: a qualified identity keeps its prefix and matches only itself."""
    if not tenant:
        return normalize_identity(identity)
    owner, rest = split_tenant(identity)
    if owner is None or owner == tenant:
        return rest
    return None


def is_agent(identity: object, bots: Collection[str] | None = None) -> bool:
    """An agent or a bot, and so never a person who decides. The one rule the gate, `aidd validate`, the waivers, the
    work items, and the explorations all ask: an `agent:` identity; a bot account; an account `identities.bots`
    names; a login the baseline names as an agent (`agent_accounts`); an agent's commit address (`agent_coauthors`
    emails and patterns); or an identity that carries a known agent's name as a whole word (`agent_coauthors` names,
    so `@claude` is one and `@claude-martin` is not). Identities are case-insensitive, and a tenant qualifier
    (`acme:agent:x`, `acme:@x`) is read through. Lookalikes are read as what they look like (`_detection_key`), and
    an identity that still holds a letter outside ASCII counts as an agent, so a person is never one by a lookalike."""
    s = _detection_key(str(identity or ""))
    if not s:
        return False
    if _non_ascii_letters(s):
        return True
    _, bare = split_tenant(s)
    if bare.startswith("agent:") or is_bot(bare):
        return True
    configured = {normalize_identity(b) for b in bots or ()}
    if s in configured or bare in configured:
        return True
    known = baseline.baseline_data()
    if bare in {normalize_identity(a) for a in known.get("agent_accounts", [])}:
        return True
    coauthors = known.get("agent_coauthors", {})
    if bare.startswith("email:"):
        address = bare.removeprefix("email:")
        if address in {e.lower() for e in coauthors.get("emails", [])}:
            return True
        if any(globs.match(p.lower(), address, fold_case=True) for p in coauthors.get("email_patterns", [])):
            return True
    return names_an_agent(s)


def names_an_agent(text: str) -> bool:
    """Whether `text` (an identity, or a co-author's name) carries a known agent's name (`agent_coauthors` names) as a
    whole word, read through lookalikes (`_detection_key`): `Claude` and `Сlaude` do, `Jean-Claude` and `claude_martin`
    do not. The one rule `is_agent` and `agent_coauthors` share."""
    s = _detection_key(text)
    names = [n.lower() for n in baseline.baseline_data().get("agent_coauthors", {}).get("names", [])]
    return any(re.search(rf"(?<![a-z0-9_-]){re.escape(n)}(?![a-z0-9_-])", s) for n in names)


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

    An agent is recognized by its e-mail (the baseline's `agent_coauthors`, or `email:<address>` in
    `identities.bots`) or by a name that carries a known agent name as a whole word.
    """
    known = baseline.baseline_data().get("agent_coauthors", {})
    emails = {e.lower() for e in known.get("emails", [])}
    patterns = [p.lower() for p in known.get("email_patterns", [])]
    bot_ids = {normalize_identity(b) for b in (bots or set())}
    out: list[str] = []
    for m in COAUTHOR.finditer(message):
        name, email = m.group(1).strip(), m.group(2).strip().lower()
        agent = email in emails or f"email:{email}" in bot_ids or any(globs.match(p, email, fold_case=True) for p in patterns)
        agent = agent or names_an_agent(name)
        if agent:
            out.append(f"{name} <{email}>" if name else email)
    return out


LOGIN_PROBES: tuple[tuple[str, ...], ...] = (("git", "config", "github.user"), ("gh", "config", "get", "-h", "github.com", "user"))


EMAIL_PROBE: tuple[str, ...] = ("git", "config", "user.email")


def _probe(cmd: tuple[str, ...], root: Path) -> str | None:
    if shutil.which(cmd[0]) is None:
        return None
    try:
        r = subprocess.run(list(cmd), cwd=str(root), capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def gh_account_count(host: str = "github.com") -> int:
    """How many accounts gh holds for `host`, read from its hosts.yml (local only; 0 when it cannot be read). gh's
    active account is one machine-wide choice, so with more than one it says nothing about this repository."""
    folder = os.environ.get("GH_CONFIG_DIR") or os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "gh")
    try:
        lines = Path(folder, "hosts.yml").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return 0
    host_at = next((i for i, line in enumerate(lines) if line.rstrip() == f"{host}:"), None)
    if host_at is None:
        return 0
    block = []
    for line in lines[host_at + 1 :]:
        if line.strip() and not line.startswith(" "):
            break  # the next host
        block.append(line)
    users = next((i for i, line in enumerate(block) if line.strip() == "users:"), None)
    if users is None:  # gh before multiple accounts: one `user:` line
        return int(any(line.strip().startswith("user:") for line in block))
    depth = len(block[users]) - len(block[users].lstrip(" "))
    names = []
    for line in block[users + 1 :]:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent <= depth:
            break
        names.append(indent)
    return names.count(min(names)) if names else 0


def operator_login(root: Path) -> str | None:
    """The operator's GitHub login from local configuration only: `git config github.user`, which follows this
    repository's own git identity, then gh's stored user, only while gh holds one account for github.com: with more,
    gh's active account is a machine-wide choice, and may be another identity's."""
    for cmd in LOGIN_PROBES:
        if cmd[0] == "gh" and gh_account_count() > 1:
            continue
        login = (_probe(cmd, root) or "").lstrip("@")
        if re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", login):
            return login
    return None


def operator_email(root: Path) -> str | None:
    """The email the operator's commits carry (`git config user.email`): a solo approver with no platform login, which
    is what local approvals (`aidd approve`) are checked against."""
    email = _probe(EMAIL_PROBE, root) or ""
    return email if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) else None


def unlisted_local_approver(root: Path, approvers: list[str]) -> str | None:
    """Why a local-first solo repository's approvals would never count: an approval from this machine counts as the
    operator's email, which `approvers` does not list (a `@login` alone never matches with no platform). None when it
    does, or when git names no email."""
    email = (operator_email(root) or "").lower()
    if not email or f"email:{email}" in {normalize_identity(a) for a in approvers}:
        return None
    return (
        f"local-first: an approval from this machine counts as email:{email}, which owners.approvers ({', '.join(approvers)}) "
        f'does not list. So `aidd approve` would record approvals the gate never counts. Add "email:{email}" to owners.approvers'
    )


def agent_account(user: str, bots: set[str] | frozenset[str] = frozenset()) -> bool:
    """An account that is an agent, whatever a pool says: listed in identities.bots, a login the baseline names as an
    agent (`agent_accounts`, such as Copilot's reviewer), or a `[bot]` account whose name carries a known agent name."""
    if user in bots or user in {normalize_identity(a) for a in baseline.baseline_data().get("agent_accounts", [])}:
        return True
    if not user.endswith("[bot]"):
        return False
    names = {n.lower() for n in baseline.baseline_data().get("agent_coauthors", {}).get("names", [])}
    return bool(names & set(re.split(r"[^a-z0-9]+", user[: -len("[bot]")])))
