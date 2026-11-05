"""Identities: who is a person, a bot, or an agent; logins normalized; the agents a commit's trailers name; and the
operator this machine's git and gh sign in as."""

from __future__ import annotations

import re
import unicodedata

from aidd.kernel import documents, globs, resources

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


# `<tenant>:<identity>`: an identity qualified with its tenant. `email:` and `agent:` are identity types, never tenants.
_TENANT_QUALIFIED = re.compile(r"^([a-z0-9][a-z0-9-]{1,62}):(\S+)$")


_IDENTITY_TYPES = ("email", "agent")


def split_tenant(identity: str) -> tuple[str | None, str]:
    """(tenant, the identity without it), normalized: `acme:@alice` is ("acme", "alice"); `alice` and `email:a@b.c` have no tenant."""
    s = normalize_identity(identity)
    m = _TENANT_QUALIFIED.match(s)
    if not m or m.group(1) in _IDENTITY_TYPES:
        return None, s
    return m.group(1), normalize_identity(m.group(2))


def is_agent(identity: object) -> bool:
    """An agent or a bot, and so never a person who decides. The one rule `aidd validate`, the waivers, the work items,
    and the explorations all ask: an `agent:` identity; a bot account;
    a login schemas/agents.json names as an agent (`agent_accounts`); an agent's commit address (`agent_coauthors`
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
    known = resources.load_json("agents.json")
    if bare in {normalize_identity(a) for a in known.get("agent_accounts", [])}:
        return True
    if bare.startswith("email:") and _agent_address(bare.removeprefix("email:")):
        return True
    return names_an_agent(s)


def _agent_address(address: str) -> bool:
    """Whether a commit address is an agent's or a bot's: one `agent_coauthors` lists or matches by pattern, or one
    whose local part is a bot account's (`dependabot[bot]@…`). A known agent's name inside it is not enough."""
    address = address.lower()
    coauthors = resources.load_json("agents.json").get("agent_coauthors", {})
    if address in {e.lower() for e in coauthors.get("emails", [])} or is_bot(address.partition("@")[0].rpartition("+")[2]):
        return True
    return any(globs.match(p.lower(), address, fold_case=True) for p in coauthors.get("email_patterns", []))


def names_an_agent(text: str) -> bool:
    """Whether `text` (an identity, or a co-author's name) carries a known agent's name (`agent_coauthors` names) as a
    whole word, read through compatibility forms (`_detection_key`): `Claude`, `Devin Lee`, and a fullwidth `Ｃlaude`
    do; `Jean-Claude` and `claude_martin` do not. It folds no other script, so a Cyrillic `Сlaude` does not, and
    `is_agent` catches that as a letter outside ASCII. The one rule `is_agent` and `agent_coauthors` share."""
    s = _detection_key(text)
    names = [n.lower() for n in resources.load_json("agents.json").get("agent_coauthors", {}).get("names", [])]
    return any(re.search(rf"(?<![a-z0-9_-]){re.escape(n)}(?![a-z0-9_-])", s) for n in names)


# Who said yes, in the form `approved_by` in schemas/common.schema.json gives: git's trailer form `Name <email>`, with
# no `(),;` and at most 80 characters in the name, or an Approver's `@handle`, `@org/team`, or `email:<address>`.
_NAME_EMAIL = re.compile(r"([^<>@\s(),;][^<>@(),;]{0,79}) <([^<>\s@]+@[^<>\s@]+)>")  # linear: the name stops at `<`
_HANDLE = re.compile(r"@[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?(?:/[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)?")
_EMAIL_IDENTITY = re.compile(r"email:[^<>\s@]+@[^<>\s@]+")


def _agent_name(name: str) -> bool:
    """Whether a whole `Name` is an agent's or a bot's: `Claude`, `copilot-swe-agent`, `github-actions[bot]`. A part of a
    name never is, so `Devin Lee` is a person, and a letter outside ASCII is a person's accent here, never a sign."""
    s = _detection_key(name)
    known = resources.load_json("agents.json")
    names = {n.lower() for n in known.get("agent_coauthors", {}).get("names", [])}
    return is_bot(s) or s in names or s in {normalize_identity(a) for a in known.get("agent_accounts", [])}


def approved_by_kind(value: str) -> str | None:
    """What is wrong with a value that names the person who said yes: `agent` when it names an agent or a bot, `form`
    when it is not one of the forms `_NAME_EMAIL`, `_HANDLE`, and `_EMAIL_IDENTITY` read, and None when it is a person
    in one of them. An address is judged as an address and a name as a whole, never by a part, so `Devin Lee
    <devin@example.com>` is a person; a handle is judged by `is_agent`."""
    written = value.strip()
    if named := _NAME_EMAIL.fullmatch(written):
        return "agent" if _agent_name(named.group(1)) or _agent_address(named.group(2)) else None
    if _EMAIL_IDENTITY.fullmatch(written):
        return "agent" if _agent_address(written.removeprefix("email:")) else None
    if _HANDLE.fullmatch(written):
        return "agent" if is_agent(written) else None
    return "form"


def approved_by_problem(value: str, field: str = "approved_by") -> str | None:
    """The warning for a `field` that holds `value` as the person who said yes, with the fix; None when it is a person
    in the form `approved_by_kind` reads."""
    shown = documents.one_line(value, 120).replace("`", "'")
    kind = approved_by_kind(value)
    if kind == "agent":
        return f"{field} `{shown}` names an agent or a bot, but only a person says yes; write the `Name <email>` or `@handle` of the person who said it"
    if kind == "form":
        return (
            f"{field} `{shown}` is not `Name <email>` or `@handle`; write only who said yes, from `git config user.name` and "
            "`git config user.email`, or the `@handle` they give, and put any detail in the commit body or the decision record"
        )
    return None


def display_name(value: object) -> str:
    """Who said yes, for a page a client may read: the name of a `Name <email>` and the local part of an `email:`
    address, so no address is copied; any other value as it is."""
    written = str(value or "").strip()
    if named := _NAME_EMAIL.fullmatch(written):
        return named.group(1)
    return written.removeprefix("email:").partition("@")[0] if _EMAIL_IDENTITY.fullmatch(written) else written
