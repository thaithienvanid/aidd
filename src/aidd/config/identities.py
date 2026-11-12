"""Identities: who is a person, a bot, or an agent; logins normalized; the agents a commit's trailers name; and the
operator this machine's git and gh sign in as."""

from __future__ import annotations

import functools
import re
import unicodedata

from aidd.kernel import documents, globs, resources, secret_patterns

BOT_ACCOUNTS = ("web-flow", "github-actions", "ghost")
NOREPLY_DOMAIN = "users.noreply.github.com"


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
    """An identity as `is_agent` reads it: as the secret scan and the delegate's tripwire read text (`secret_patterns.comparable`:
    NFKC-folded, so a fullwidth `ａgent` is `agent`, and without zero-width and other format characters), then normalized. Never an
    equality key for an allow-list."""
    return normalize_identity(secret_patterns.comparable(identity))


def _fold_accents(text: str) -> str:
    """`text` without the accents on its Latin letters (`José` is `Jose`, `Nguyễn` is `Nguyen`): decomposed, its combining
    marks dropped, and composed again. A letter with no decomposition, such as `ø`, stays."""
    decomposed = unicodedata.normalize("NFKD", text)
    return unicodedata.normalize("NFC", "".join(c for c in decomposed if unicodedata.category(c) not in ("Mn", "Me")))


def _agent_key(text: str) -> str:
    """`text` as agent detection reads it: `_detection_key`, then without Latin accents, so `cláude` is `claude`."""
    return _fold_accents(_detection_key(text))


def _stray_mark(identity: str) -> bool:
    """True when a combining mark follows a Latin letter and no composed letter holds the pair, such as `u` and a macron
    below in `clau̱de`: an accent no real name needs, which only hides a word from a reader (fail-closed)."""
    composed = unicodedata.normalize("NFC", identity)
    return any(unicodedata.category(c) in ("Mn", "Me") and i > 0 and unicodedata.name(composed[i - 1], "").startswith("LATIN") for i, c in enumerate(composed))


def _latin(c: str) -> bool:
    """Whether a letter is one a Latin-script name needs: ASCII, or U+00C0 to U+024F (Latin-1 Supplement and Latin
    Extended-A and B: `ø`, `Ł`, `Đ`, `ß`, `Æ`, `Œ`, `Þ`, `ı`, `Ħ`, `Ə`). The lookalikes outside it (`ɑ`, `ᴄ`, `ɡ`) are not."""
    return c.isascii() or any(0xC0 <= ord(x) <= 0x24F for x in (c, c.upper()))  # `ə` is kept as the lowercase of `Ə`


def _non_latin_letters(identity: str) -> bool:
    """True when a letter outside `_latin` is left after folding, such as a Cyrillic `а` in `clаude` or an IPA `ɑ` in `clɑude`:
    a login, an `agent:` name, or a known agent's name could hide behind it, so it is read as an agent (fail-closed)."""
    return any(c.isalpha() and not _latin(c) for c in identity)


def _mixed_script(text: str) -> bool:
    """True when one word of `text` holds Latin letters and letters of another script (Unicode TR39, mixed script): `Сlaude`
    with a Cyrillic `С`. A word wholly in another script is a person's name in that script."""
    for word in re.split(r"[^\w]+", text):
        letters = [c for c in word if c.isalpha()]
        if any(_latin(c) for c in letters) and not all(_latin(c) for c in letters):
            return True
    return False


# `<tenant>:<identity>`: an identity qualified with its tenant. A type's name (`identity_types`) is never a tenant's.
_TENANT_QUALIFIED = re.compile(r"^([a-z0-9][a-z0-9-]{1,62}):(\S+)$")


@functools.cache
def identity_types() -> dict[str, str]:
    """Each type of a typed identity `<type>:<value>`, and whether it names a `person` or an `agent`: the `x-who` of `identity` in
    schemas/common.schema.json, the one statement of the grammar. Read when first asked, never on import."""
    return dict(resources.load_json("common.schema.json")["$defs"]["identity"]["x-who"])


def _agent_prefixes() -> tuple[str, ...]:
    """The prefixes of the types that name an agent (`agent:`, `role:`): such an identity is never a person who decides."""
    return tuple(f"{kind}:" for kind, who in identity_types().items() if who == "agent")


def split_tenant(identity: str) -> tuple[str | None, str]:
    """(tenant, the identity without it), normalized: `acme:@alice` is ("acme", "alice"); `alice` and `email:a@b.c` have no tenant."""
    s = normalize_identity(identity)
    m = _TENANT_QUALIFIED.match(s)
    if not m or m.group(1) in identity_types():
        return None, s
    return m.group(1), normalize_identity(m.group(2))


def typed_identity(identity: object) -> tuple[str | None, str]:
    """(its type, its value) as `is_agent` reads an identity: folded, without accents, case-insensitive, and through a tenant, so
    `Role:Architect` is ("role", "architect") and `acme:agent:x` is ("agent", "x"). A login has no type: `@alice` is (None, "alice")."""
    _, bare = split_tenant(_agent_key(str(identity or "")))
    kind, colon, value = bare.partition(":")
    return (kind, value) if colon and kind in identity_types() else (None, bare)


def is_agent(identity: object) -> bool:
    """An agent or a bot, and so never a person who decides. The one rule `aidd validate`, the waivers, the work items,
    and the explorations all ask: an `agent:` or a `role:` identity; a bot account;
    a login schemas/agents.json names as an agent (`agent_accounts`); an agent's commit address (`agent_coauthors`
    emails and patterns); an agent's whole name (`_whole_agent_names`, which `approved_by_kind` reads too); or an identity that carries a known agent's name as a whole word (`agent_coauthors` names,
    so `@claude` is one and `@claude-martin` is not). Identities are case-insensitive, and a tenant qualifier
    (`acme:agent:x`, `acme:@x`) is read through. Lookalikes are read as what they look like (`_detection_key`), and
    an identity that still holds a letter outside the Latin script, or an accent no letter holds, counts as an agent, so a
    person is never one by a lookalike. Accents on Latin letters are folded away: `José` is a person, and `cláude` is `claude`."""
    raw = _detection_key(str(identity or ""))
    if not raw:
        return False
    if _stray_mark(raw):
        return True
    s = _fold_accents(raw)
    if _non_latin_letters(s):
        return True
    _, bare = split_tenant(s)
    if bare.startswith(_agent_prefixes()) or is_bot(bare):
        return True
    named = _NAME_EMAIL.fullmatch(str(identity or "").strip())
    if named and _agent_name(named.group(1)):
        return True
    if bare.startswith("email:") and _agent_address(bare.removeprefix("email:")):
        return True
    return _agent_name(bare) or names_an_agent(s)


def _agent_address(address: str) -> bool:
    """Whether a commit address is an agent's or a bot's: one `agent_coauthors` lists (with or without a `+tag` in its local
    part: `noreply+x@anthropic.com` is `noreply@anthropic.com`) or matches by pattern, or one whose local part is a bot
    account's (`dependabot[bot]@…`), or GitHub's no-reply address of an agent account (`12345+Copilot@users.noreply.github.com`),
    under any display name. A known agent's name inside it is not enough."""
    address = address.lower()
    local, _, domain = address.partition("@")
    coauthors = resources.load_json("agents.json").get("agent_coauthors", {})
    listed = {e.lower() for e in coauthors.get("emails", [])}
    if address in listed or f"{local.partition('+')[0]}@{domain}" in listed or is_bot(local.rpartition("+")[2]):
        return True
    number, plus, login = local.partition("+")  # GitHub's no-reply address, `<digits>+<login>@users.noreply.github.com`
    if domain == NOREPLY_DOMAIN and plus and number.isdigit() and login in {a.lower() for a in resources.load_json("agents.json").get("agent_accounts", [])}:
        return True
    return any(globs.match(p.lower(), address, fold_case=True) for p in coauthors.get("email_patterns", []))


def names_an_agent(text: str) -> bool:
    """Whether `text` (an identity, or a co-author's name) carries a known agent's name (`agent_coauthors` names) as a
    whole word, read through compatibility forms (`_detection_key`): `Claude`, `Devin Lee`, and a fullwidth `Ｃlaude`
    do; `Jean-Claude` and `claude_martin` do not. It folds no other script, so a Cyrillic `Сlaude` does not, and
    `is_agent` catches that as a letter outside ASCII. The one rule `is_agent` and `agent_coauthors` share."""
    s = _agent_key(text)
    names = [n.lower() for n in resources.load_json("agents.json").get("agent_coauthors", {}).get("names", [])]
    return any(re.search(rf"(?<![a-z0-9_-]){re.escape(n)}(?![a-z0-9_-])", s) for n in names)


# Who said yes, in the form `approved_by` in schemas/common.schema.json gives: git's trailer form `Name <email>`, with at
# most 80 characters in the name, or an Approver's `@handle`, `@org/team`, or `email:<address>`. A name may hold `(),;`
# (`Lee, Devin`, `Devin Lee (he/him)`): `_name_parts` reads it, so a part in round brackets is judged on its own. With
# more than `_MAX_NOTE_WORDS` words it is a note, never a name (`Maya, as the owner's delegate (record of 2026-11-07)`).
_NAME_EMAIL = re.compile(r"([^<>@\s][^<>@]{0,79}) <([^<>\s@]+@[^<>\s@]+)>")  # linear: the name stops at `<`
_MAX_NOTE_WORDS = 6
_HANDLE = re.compile(r"@[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?(?:/[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)?")
_EMAIL_IDENTITY = re.compile(r"email:[^<>\s@]+@[^<>\s@]+")
_BARE_ADDRESS = re.compile(r"<([^<>\s@]+@[^<>\s@]+)>")  # an address with no name


def _squash(name: str) -> str:
    """A name as it is compared as a whole: a run of spaces, tabs, `-`, `_`, `,`, and `;` is one space, and a `.` or `!` at the end is
    gone. So `Claude  Code`, `Claude-Code`, `Claude_Code`, and `Claude Code!` are `claude code`, `Claude.` is `claude`, and `Claude M.`,
    `Lee, Devin`, and `Cody Bot-Hansen` are none of a listed name's."""
    return re.sub(r"[\s_,;-]+", " ", name).strip().rstrip(".! ")


def _name_parts(name: str) -> list[str]:
    """The whole names `name` holds, each squashed (`_squash`) and none empty: what stands outside round brackets as one, and what stands
    inside each pair of brackets as one of its own. `Maya (aider)` is `maya` and `aider`, and `Devin Lee (he/him)` is `devin lee` and
    `he/him`. A bracket left open holds to the end, and one left closed is a space, so a name never hides a part behind it. One pass."""
    key = _agent_key(name)
    if "(" not in key and ")" not in key:
        return [part for part in (_squash(key),) if part]
    parts: list[str] = []
    open_parts: list[list[str]] = [[]]
    for c in key:
        if c == "(":
            open_parts.append([])
        elif c == ")" and len(open_parts) > 1:
            parts.append("".join(open_parts.pop()))
            open_parts[-1].append(" ")
        elif c == ")":
            open_parts[0].append(" ")
        else:
            open_parts[-1].append(c)
    parts += ("".join(p) for p in open_parts)
    return [part for part in map(_squash, parts) if part]


@functools.cache
def _whole_agent_names() -> frozenset[str]:
    """Every whole name that is an agent's or a bot's, squashed (`_squash`), the one list `is_agent` and `approved_by_kind` read: the
    product names of `agent_coauthors` in schemas/agents.json (`names`, and `full_names` for a name with its vendor or a generic `agent` or `bot`),
    each coding agent's own name as the harness table gives it (`Claude Code`, `GitHub Copilot`), and each agent account. A name
    that only holds one of these is no member: `Devin Lee` and `Abbot` are people."""
    known = resources.load_json("agents.json")
    coauthors = known.get("agent_coauthors", {})
    from aidd.config import harnesses

    labels = (h.label for h in harnesses.HARNESSES.values())
    listed = [*coauthors.get("names", []), *coauthors.get("full_names", []), *labels, *known.get("agent_accounts", []), *BOT_ACCOUNTS]
    return frozenset(_squash(_agent_key(n)) for n in listed)


def _name_email(written: str) -> re.Match[str] | None:
    """`written` as `Name <email>` when it is a name and not a note: a name with `(),;` and more than `_MAX_NOTE_WORDS` words is a note a
    person put where only who said yes goes, so it is in no form (`approved_by_kind` says `form`, or `agent` where it holds an agent's word)."""
    named = _NAME_EMAIL.fullmatch(written)
    return None if named and len(named.group(1).split()) > _MAX_NOTE_WORDS and re.search(r"[(),;]", named.group(1)) else named


def _agent_name(name: str) -> bool:
    """Whether a `Name` is an agent's or a bot's, the one function every door reads (`approver_is_agent`, `approved_by_kind`, and
    `is_agent`): each of its parts (`_name_parts`) is judged as a whole, after `_squash`. `Claude`, `Claude  Code`, `Claude-Code`, `Claude.`,
    `bot`, `copilot-swe-agent`, `github-actions[bot]`, and `Maya (aider)` are an agent's. A part of a name never is, so `Devin Lee`,
    `Lee, Devin`, `Devin Lee (he/him)`, and `Cody Bot-Hansen` are people, and an accent on a Latin letter is a person's accent here.
    A listed name that stands beside other words is a person's, a stated limit (SECURITY.md): the words may follow it (`Claude Bot`,
    `Gemini CLI`), or a person's name may come first with a comma or a semicolon (`Jane Roe, Claude Code`). In round brackets it is refused."""
    return any(is_bot(part) or part in _whole_agent_names() for part in _name_parts(name))


def approved_by_kind(value: str) -> str | None:
    """What is wrong with a value that names the person who said yes: `agent` when it names an agent or a bot, `form`
    when it is not one of the forms `_NAME_EMAIL`, `_HANDLE`, and `_EMAIL_IDENTITY` read, and None when it is a person
    in one of them. It answers `agent` whenever any test aidd has asked of an approver does: an `agent:` or a `role:` identity,
    tenant-qualified or not, even before an address, read through compatibility forms and without accents; in a handle or an
    address, an accent no letter holds; a name that is an agent's whole name, or mixes Latin letters with another script in
    one word; an agent's address, with an empty name or a `+tag` too, or one with such a mixed word; and, for a value in no
    form, `is_agent`. A name wholly in another script that only looks like an agent's reads as a person: this is a tripwire
    for honest mistakes and plain agent names, not a control (SECURITY.md). A name is judged as a whole after one normalising step (`_agent_name`), never by a part, so `Claude  Code` and
    `Claude-Code` are agents, and `Devin Lee <devin@example.com>`, `Lee, Devin`, and `José García <jose@example.com>` are people. The one rule the waivers, `--approvers`, an Intent's agreement, and a Spec's
    `approved_by` ask."""
    written = value.strip()
    key = _agent_key(written)  # folded: `agént:dev` is `agent:dev`, and a zero-width character is gone
    if key.startswith(_agent_prefixes()) or any(f":{prefix}" in key for prefix in _agent_prefixes()):
        return "agent"
    named = _name_email(written)
    if not named and _stray_mark(_detection_key(written)):
        return "agent"  # a name may carry any accent (`Adéṣọ̀lá`); a handle or an address has no need of one no letter holds
    if named:
        name = _agent_key(named.group(1))
        return "agent" if _agent_name(name) or _mixed_script(name) or _agent_address_in(named.group(2)) else None
    if bare := _BARE_ADDRESS.fullmatch(written):
        return "agent" if _agent_address_in(bare.group(1)) else "form"
    if _EMAIL_IDENTITY.fullmatch(written):
        return "agent" if _agent_address_in(written.removeprefix("email:")) else None
    if _HANDLE.fullmatch(written):
        return "agent" if is_agent(written) else None
    return "agent" if is_agent(written) else "form"


def _agent_address_in(address: str) -> bool:
    """Whether an address as written is an agent's: read folded (`anthropiｃ.com` is `anthropic.com`, a zero-width character is
    gone), or with a word that mixes Latin letters with another script (`аnthropic.com` with a Cyrillic `а`)."""
    key = _agent_key(address)
    return _agent_address(key) or _mixed_script(key)


def approver_is_agent(value: str) -> bool:
    """Whether a value that names who may say yes is an agent's or a bot's, and so never a person (`approved_by_kind`)."""
    return approved_by_kind(value) == "agent"


def one_word_hint(takes_email: bool = True) -> str:
    """The way out for a person a name or an address reads as an agent's: a name that is only an agent's (`Claude`, `Claude Code`) gets a
    surname or an initial, an agent's address gets their own, and, where the door takes it, `email:<address>` stands in for both. Each door
    that refuses an agent's name says it."""
    return (
        "a name that is only an agent's, such as `Claude` or `Claude Code`, reads as one, so add a surname or an initial; "
        "an agent's address reads as one too, so use your own" + (", or write `email:<address>`" if takes_email else "")
    )


def approved_by_problem(value: str, field: str = "approved_by") -> str | None:
    """The warning for a `field` that holds `value` as the person who said yes, with the fix; None when it is a person
    in the form `approved_by_kind` reads."""
    shown = documents.one_line(value, 120).replace("`", "'")
    kind = approved_by_kind(value)
    if kind == "agent":
        return f"{field} `{shown}` names an agent or a bot, but only a person says yes; write the person's `@handle`, or the `Name <email>` they commit with ({one_word_hint()})"
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
