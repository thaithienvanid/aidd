"""Identities: who is a person, a bot, or an agent; logins normalized; the agents a commit's trailers name; and the
operator this machine's git and gh sign in as."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection

from aidd.kernel import globs, resources

BOT_ACCOUNTS = ("web-flow", "github-actions", "ghost")


def is_bot(identity: str) -> bool:
    s = identity.strip().lower().lstrip("@")
    return s.endswith("[bot]") or s in BOT_ACCOUNTS


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


def is_agent(identity: object, bots: Collection[str] | None = None) -> bool:
    """An agent or a bot, and so never a person who decides. The one rule `aidd validate`, the waivers, the work items,
    and the explorations all ask: an `agent:` identity; a bot account; an account `identities.bots`
    names; a login schemas/agents.json names as an agent (`agent_accounts`); an agent's commit address (`agent_coauthors`
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
    known = resources.load_json("agents.json")
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
    names = [n.lower() for n in resources.load_json("agents.json").get("agent_coauthors", {}).get("names", [])]
    return any(re.search(rf"(?<![a-z0-9_-]){re.escape(n)}(?![a-z0-9_-])", s) for n in names)


_NOREPLY = re.compile(r"^(?:\d+\+)?([a-z0-9](?:[a-z0-9-]{0,38}))@users\.noreply\.github\.com$")
