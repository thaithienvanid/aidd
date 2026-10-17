"""What a prompt decides, when the person types it: one parser for aidd's prompt hook (cli/commands/typed_decisions.py,
which records it) and the guard (guard/approval_commands.py, which keeps an agent from handing such a prompt to
another session as if the person typed it). aidd-mods reads the same phrases in its own code.
"""

from __future__ import annotations

import re

# The words around the ids that still make a prompt an approval: "approve SPEC-1 and SPEC-4 please".
_FILLER = frozenset({"and", "spec", "specs", "the", "both", "them", "it", "please", "pls", "now", "too", "also", "these", "those", "this"})
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9]*-[0-9]+$")
_APPROVE = re.compile(r"^\s*(?:/aidd\s+)?(?:i\s+)?approved?\b([\s\S]*)$", re.I)
_SHIP = re.compile(r"^\s*(?:/aidd\s+ship|(?:please\s+)?ship(?:\s+(?:it|this|this branch|now))?)\s*[.!]?\s*$", re.I)
_STOP = re.compile(r"^\s*(?:/aidd\s+approve\s+stop|stop\s+approving(?:\s+for\s+me)?)\s*[.!]?\s*$", re.I)
_ALL = re.compile(
    r"^\s*(?:/aidd\s+approve\s+all|(?:i\s+)?approve\s+all(?:\s+from\s+now\s+on)?|automate(?:\s+it|\s+all|\s+everything)?)"
    r"(?P<but>\s*,?\s+(?:but|except)\s+major)?\s*[.!]?\s*$",
    re.I,
)


def parse_typed(text: str) -> tuple[str, list[str]] | None:
    """What `text` decides: ("stop", []), ("all", [] or ["but-major"]), ("ship", []), ("merge", []), or ("spec", the
    ids, or [] for what waits on the person); None for any other prompt."""
    if _STOP.match(text):
        return "stop", []
    if m := _ALL.match(text):
        return "all", ["but-major"] if m.group("but") else []
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
    (`stop approving`)."""
    decided = parse_typed(text)
    return decided is not None and decided[0] != "stop"
