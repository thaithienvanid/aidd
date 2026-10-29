"""What a prompt decides, when the person types it: one parser for aidd's prompt hook (cli/commands/typed_decisions.py,
which records it) and the guard (guard/approval_commands.py, which keeps an agent from handing such a prompt to
another session as if the person typed it). aidd-mods reads the same phrases in its own code.
"""

from __future__ import annotations

import re
import unicodedata

# The words around the ids that still make a prompt an approval: "approve SPEC-1 and SPEC-4 please".
_FILLER = frozenset({"and", "spec", "specs", "the", "both", "them", "it", "please", "pls", "now", "too", "also", "these", "those", "this"})
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9]*-[0-9]+$")
_APPROVE = re.compile(r"^\s*(?:/aidd(?::aidd)?\s+)?(?:i\s+)?approved?\b([\s\S]*)$", re.I)
# The three steps after Review, each a person's own yes: land on the local trunk, publish off this machine, and merge
# the pull or merge request on the platform. `ship it` named all three once; it records nothing now, and points to them.
_LAND = re.compile(r"^\s*(?:/aidd(?::aidd)?\s+)?(?:please\s+)?land(?:\s+(?:it|this|this branch|now))?\s*[.!]?\s*$", re.I)
_MERGE_IT = re.compile(
    r"^\s*(?:/aidd(?::aidd)?\s+)?(?:please\s+)?merge(?:\s+(?:it|this|now|(?:the|this)\s+(?:pr|mr|pull\s+request|merge\s+request)))?\s*[.!]?\s*$",
    re.I,
)
_PUBLISH = re.compile(
    r"^\s*(?:(?:/aidd(?::aidd)?\s+)?(?:please\s+)?(?:publish|push)(?:\s+(?:it|this|this branch|now|to\s+(?:the\s+)?remote))?"
    r"|(?:please\s+)?(?:open|create|make)\s+(?:a|the)\s+(?:pr|mr|pull\s+request|merge\s+request))\s*[.!]?\s*$",
    re.I,
)
_SHIP = re.compile(r"^\s*(?:/aidd(?::aidd)?\s+)?(?:please\s+)?ship(?:\s+(?:it|this|this branch|now))?\s*[.!]?\s*$", re.I)
# The word that names an explore branch, in the typed words (`explore branch <topic>`) and the `/aidd` verb
# (`/aidd explore <topic>`): one place to rename it. Typed, it comes with the word "branch", so "explore auth" stays an
# ordinary prompt (and `/aidd-team:explore`, an exploration, is another thing).
EXPLORE_WORD = "explore"
_EXPLORE = re.compile(
    rf"^\s*(?:(?:start\s+an?\s+)?{EXPLORE_WORD}\s+branch|/aidd(?::aidd)?\s+{EXPLORE_WORD}(?:\s+branch)?)\s+(?:{EXPLORE_WORD}/)?"
    r"(?P<topic>[A-Za-z0-9][A-Za-z0-9._-]{0,60})\s*[.!]?\s*$",
    re.I,
)
_STOP = re.compile(r"^\s*(?:/aidd(?::aidd)?\s+(?:approve\s+)?stop|stop\s+approving(?:\s+for\s+me)?)\s*[.!]?\s*$", re.I)
_ALL = re.compile(
    r"^\s*(?:/aidd(?::aidd)?\s+approve\s+all|(?:i\s+)?approve\s+all(?:\s+from\s+now\s+on)?|automate(?:\s+it|\s+all|\s+everything)?)"
    r"(?P<pub>\s*,?\s+and\s+publish)?(?P<but>\s*,?\s+(?:but|except)\s+major)?\s*[.!]?\s*$",
    re.I,
)
_PROPOSAL_ID = r"(?P<id>[A-Za-z][A-Za-z0-9]*-[0-9]+)"
# The reason follows only a stop or `because`, so "decide PROP-1 go or no-go for me" asks, and never decides.
_DECIDE = re.compile(
    rf"^\s*(?:/aidd(?::aidd)?\s+)?decide\s+{_PROPOSAL_ID}\s+(?P<decision>go|no[\s-]go)"
    r"(?:(?:\s*[,:;.]\s*(?:because\s+)?|\s+because\s+)(?P<why>[^\r\n]*?))?\s*[.!]?\s*$",
    re.I | re.ASCII,  # as JavaScript reads it: `[A-Za-z]` never takes a dotless or a dotted i
)
_SIGN_OFF = re.compile(rf"^\s*(?:/aidd(?::aidd)?\s+)?sign[\s-]?off\s+{_PROPOSAL_ID}\s*[.!]?\s*$", re.I | re.ASCII)


# Direction controls, which reorder what a screen shows: `approve SPEC-<RLO>12` shows as SPEC-21 and reads as SPEC-12.
_BIDI = re.compile("[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def plain_typed(text: str) -> str:
    """A prompt as aidd reads it for a decision, the same in every harness (aidd-mods' plainTyped does the same): NFKC
    (a fullwidth `ａpprove` is `approve`), without format characters (zero-width spaces and joiners, a byte-order
    mark), and with every other space character as a plain space. So words a person typed with an input method, or
    text pasted with invisible characters, decide what they read as. A prompt with a direction control, or a character
    other than a fullwidth digit that folds to a digit, is "", which decides nothing: what the screen shows may not be
    what it says."""
    if _BIDI.search(text) or any(
        not c.isascii() and not "\uff10" <= c <= "\uff19" and any(d in "0123456789" for d in unicodedata.normalize("NFKC", c)) for c in text
    ):
        return ""  # nor one where folding makes a digit from another shape (`SPEC-1¹` would read SPEC-11); fullwidth reads as it shows
    folded = unicodedata.normalize("NFKC", text)
    return "".join(" " if unicodedata.category(c) == "Zs" else c for c in folded if unicodedata.category(c) != "Cf")


def parse_typed(text: str) -> tuple[str, list[str]] | None:
    """What `text` decides: ("stop", []), ("all", [] with "and-publish" and "but-major" when said), ("land", []), ("publish", []), ("merge-it", []),
    ("merge", []) for a Merge approval alone, ("spec", the ids, or [] for what waits on the person), ("decide",
    [proposal, go or no-go, reason]), ("sign-off", [proposal]), or ("explore", [topic]) for an explore branch, and ("ship", []) for the retired
    `ship it`, which decides nothing. None for any other prompt. It reads `text` as plain_typed gives it."""
    text = plain_typed(text)
    if m := _DECIDE.match(text):
        decision = "no-go" if m.group("decision").lower().startswith("no") else "go"
        return "decide", [m.group("id").upper(), decision, (m.group("why") or "")[:500]]
    if m := _SIGN_OFF.match(text):
        return "sign-off", [m.group("id").upper()]
    if m := _EXPLORE.match(text):
        return "explore", [m.group("topic")]
    if _STOP.match(text):
        return "stop", []
    if m := _ALL.match(text):
        return "all", [*(["and-publish"] if m.group("pub") else []), *(["but-major"] if m.group("but") else [])]
    if _LAND.match(text):
        return "land", []
    if _MERGE_IT.match(text):
        return "merge-it", []
    if _PUBLISH.match(text):
        return "publish", []
    if _SHIP.match(text):
        return "ship", []
    m = _APPROVE.match(text)
    if not m:
        return None
    ids: list[str] = []
    merge = False
    for word in (w for w in re.split(r"[\s,.;!&+]+", m.group(1)) if w):
        if _ID.match(word):
            ids.append(word.upper())
        elif re.fullmatch(r"merg(?:e|ing)", word, re.I):
            merge = True
        elif word.lower() not in _FILLER:
            return None
    if merge:
        return ("merge", []) if not ids else None
    return "spec", list(dict.fromkeys(ids))


def grants(text: str) -> bool:
    """Whether `text`, typed by the person, would grant or loosen something: any decision but taking one back
    (`stop approving`) or the retired `ship it`, which records nothing."""
    decided = parse_typed(text)
    return decided is not None and decided[0] not in ("stop", "ship")
