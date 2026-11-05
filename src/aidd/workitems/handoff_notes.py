"""The handoff note: the `aidd-handoff` block a role ends each run with, the latest one a document holds, and what it asks a person for."""

from __future__ import annotations

import functools
import re
import unicodedata

from aidd.kernel import documents, json_schema, resources, strict_yaml

# Approvals that a handoff note must not name as its `next`. The Approver inbox follows the derived status, so a note
# names the role that takes the work, and `aidd validate` warns about one of these.
APPROVAL_STEPS = ("spec-approval", "merge-approval")
HANDOFF_SCHEMA = "handoff.schema.json"
HANDOFF_FENCE = re.compile(r"^```aidd-handoff[ \t]*\r?\n(.*?)^```[ \t]*$", re.S | re.M)


@functools.cache
def handoff_keys() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The note's required keys and its optional keys, as schemas/handoff.schema.json lists them: its one owner."""
    schema = resources.load_json(HANDOFF_SCHEMA)
    required = tuple(schema["required"])
    return required, tuple(k for k in schema["properties"] if k not in required)


@functools.cache
def role_ids() -> frozenset[str]:
    return frozenset(resources.load_json("roles.json")["roles"])


def handoff_raw_blocks(text: str) -> list[str]:
    """The text of every ```aidd-handoff block in a document, in order."""
    return [m.group(1) for m in HANDOFF_FENCE.finditer(text)]


def handoff_blocks(text: str) -> list[tuple[str, dict | None, str]]:
    """Every ```aidd-handoff block in a document, in order and in one pass of the fence pattern: (its text, its YAML as
    a dict or None, and the parse error)."""
    out: list[tuple[str, dict | None, str]] = []
    for raw in handoff_raw_blocks(text):
        try:
            out.append((raw, documents.parse_yaml(raw, "aidd-handoff block"), ""))
        except documents.DocumentError as exc:
            out.append((raw, None, str(exc)))
    return out


# Characters a reader cannot see but a model reads. Format characters (zero-width, bidi marks and overrides, the soft
# hyphen, the byte order mark), line and paragraph separators, control characters other than tab and line breaks, the
# Unicode tag block, variation selectors that carry data, and letters and signs that draw nothing.
_INVISIBLE_LETTERS = frozenset("\u034f\u115f\u1160\u17b4\u17b5\u2800\u3164\uffa0")
_JOINERS = "\u200c\u200d"
# A reader never sees a hidden text past this many characters of a block (a document is capped at documents.MAX_DOCUMENT_BYTES).
SCAN_LIMIT = documents.MAX_DOCUMENT_BYTES


def _is_hidden(ch: str, before: str, after: str) -> bool:
    cp = ord(ch)
    if ch in _JOINERS:
        # A joiner is legitimate between two letters or symbols outside ASCII (emoji sequences, Persian and Indic
        # scripts), never beside ASCII, another joiner, punctuation, or a space.
        return any(c.isascii() or c in _JOINERS or unicodedata.category(c)[0] in "PZ" for c in (before, after))
    if ch in "\ufe0e\ufe0f":
        # The text and emoji presentation selectors follow a symbol, or a keycap's digit before U+20E3; a run of them,
        # or one after a letter, carries nothing a reader sees.
        return before in "\ufe0e\ufe0f" or (before.isascii() and after != "\u20e3") or before.isalpha()
    if 0xE0000 <= cp <= 0xE0FFF or 0xFE00 <= cp <= 0xFE0D or 0x180B <= cp <= 0x180F or ch in _INVISIBLE_LETTERS:
        return True
    cat = unicodedata.category(ch)
    return cat in ("Cf", "Zl", "Zp") or (cat == "Cc" and ch not in "\t\n\r")


def hidden_characters(text: str) -> list[str]:
    """The distinct hidden characters in `text` as `U+XXXX NAME`, in the order they first appear. It reads at most
    SCAN_LIMIT characters, and one linear pass."""
    found: dict[str, str] = {}
    s = text[:SCAN_LIMIT]
    for i, ch in enumerate(s):
        if ord(ch) > 0x7E or ord(ch) < 0x20:
            if ch not in found and _is_hidden(ch, s[i - 1] if i else " ", s[i + 1] if i + 1 < len(s) else " "):
                found[ch] = f"U+{ord(ch):04X} {unicodedata.name(ch, 'unnamed')}"
    return list(found.values())


# Text that poses as a person's words or a harness frame. A note is a report from an agent, so a line that reads as a
# person's turn, a person's yes, or a frame the harness writes is data posing as something else. Each pattern is
# checked against one line, at most _LINE_LIMIT characters, after NFKC folding and the removal of hidden characters.
_LINE_LIMIT = 300
# Each line is read in windows of _LINE_LIMIT characters that overlap by more than any pattern's length, so text far
# along a long line is read too, and the cost stays linear.
_WINDOW_STEP = 200
_SENTENCE = re.compile(r"(?<=[.!?;])\s+")
_TURN_START = (
    re.compile(r"(?:human|user|assistant|system|developer|person|ai|owner|lead|approver)[ \t]{0,3}[:>]"),
    re.compile(r"#{1,6}[ \t]{0,3}(?:human|user|assistant|system|instructions?)\b"),
)
_APPROVAL_START = (
    re.compile(r"(?:approved[,!;:]|lgtm|go ahead|i approve|approval granted|permission granted)\b"),
    re.compile(r"yes\b[\s,.!]{0,3}(?:go ahead|approved?|proceed|merge|push|do it|you may)"),
)
_FRAME = re.compile(
    r"<\|[a-z_]{1,32}\|>|\[/?(?:inst|sys|system)\]|<</?sys>>"
    r"|</?(?:system|user|assistant|human|developer|system-reminder|tool_use|tool_result|function_calls|invoke|command-name|antml:[a-z_]{1,40})\b[^>\n]{0,80}>"
)
_APPROVAL_CLAIM = re.compile(
    r"\b(?:approved by|approval (?:granted|given)|i (?:hereby )?approve"
    r"|(?:person|human|user|owner|lead|approver|maintainer|reviewer)[ \t]+(?:has |had )?(?:said|says|replied|confirmed|approved|approves|agreed|granted))\b"
)


def posing_lines(text: str) -> list[str]:
    """Each type of text in `text` that poses as a person's words or a harness frame: a chat turn marker, a harness
    frame, or a claim of approval, in the order found, once each. `text` is split into lines of at most _LINE_LIMIT
    characters, so a long input never costs more than its length."""
    poses: list[str] = []
    for line in text[:SCAN_LIMIT].splitlines():
        for start in range(0, max(len(line), 1), _WINDOW_STEP):
            folded = unicodedata.normalize("NFKC", line[start : start + _LINE_LIMIT])
            folded = "".join(c for c in folded if not _is_hidden(c, "", "")).casefold()
            leads = [s.lstrip(" \t>*_-\"'`") for s in _SENTENCE.split(folded)]
            found = (
                ("a chat turn marker", any(p.match(lead) for lead in leads for p in _TURN_START)),
                ("a harness frame", bool(_FRAME.search(folded))),
                ("a claim of approval", any(p.match(lead) for lead in leads for p in _APPROVAL_START) or bool(_APPROVAL_CLAIM.search(folded))),
            )
            poses += [pose for pose, hit in found if hit and pose not in poses]
            if start + _LINE_LIMIT >= len(line):
                break
    return poses


def _strings(node: object, depth: int = 0) -> list[str]:
    """Every key and every string in a parsed note, so an escape such as `\\u200b` in a quoted value is read as the
    character it makes."""
    if depth > strict_yaml.MAX_DEPTH:
        return []
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [t for k, v in node.items() for t in (_strings(k, depth + 1) + _strings(v, depth + 1))]
    if isinstance(node, list):
        return [t for v in node for t in _strings(v, depth + 1)]
    return []


def _text_warnings(where: str, i: int, raw: str, note: dict | None) -> list[str]:
    """Warnings for hidden characters and posing text in one note: its raw text, and the strings it parses to."""
    texts = [raw] + _strings(note)
    out = []
    hidden = list(dict.fromkeys(h for t in texts for h in hidden_characters(t)))
    if hidden:
        shown = ", ".join(hidden[:4]) + (f", and {len(hidden) - 4} more" if len(hidden) > 4 else "")
        out.append(
            f"warning: {where}: handoff note {i} holds hidden characters ({shown}). A reader cannot see them but a model reads them. "
            "Delete them, or write the note again in plain text"
        )
    posing = list(dict.fromkeys(k for t in texts for k in posing_lines(t)))
    if posing:
        out.append(
            f"warning: {where}: handoff note {i} holds text that poses as a person's words or a harness frame ({', '.join(posing)}). "
            "A note is data: it never says what a person decided. Rewrite that line as a report of what you did, and let the person answer in the chat"
        )
    return out


def handoff_warnings(where: str, text: str) -> list[str]:
    """`aidd validate` warnings for handoff notes a reader cannot use: bad YAML, a missing key, a key or a value that
    breaks schemas/handoff.schema.json, a `next` that is not a role (an approval is not a role: the person decides it),
    an unknown `status`, hidden characters, or text posing as a person's words. They advise and block nothing."""
    from aidd.workitems.status import SPEC

    required, optional = handoff_keys()
    out = []
    for i, (raw, note, err) in enumerate(handoff_blocks(text), 1):
        out += _text_warnings(where, i, raw, note)
        if note is None:
            out.append(f"warning: {where}: handoff note {i} is not YAML ({err.split(': ', 1)[-1]})")
            continue
        missing = [k for k in required if k not in note]
        unknown = sorted(set(note) - set(required) - set(optional))
        if missing:
            out.append(f"warning: {where}: handoff note {i} has no {', '.join(missing)}")
        if unknown:
            out.append(f"warning: {where}: handoff note {i} has keys aidd does not read: {', '.join(unknown)}")
        # The schema also types each value. `next` and `status` have the messages below, and a missing or unknown key the
        # messages above, so only a value's own type error (`$.done: expected string`) is added here.
        for e in json_schema.validate(note, HANDOFF_SCHEMA):
            if e.startswith("$.") and not e.startswith(("$.next", "$.status")):
                out.append(f"warning: {where}: handoff note {i}: {e[2:]}")
        nxt = note.get("next")
        if nxt in APPROVAL_STEPS:
            out.append(
                f"warning: {where}: handoff note {i}: next {nxt!r} is an approval, not a role. aidd puts the Spec in the Approver "
                "inbox from its derived status. Name the role that takes the work next"
            )
        elif "next" in note and (not isinstance(nxt, str) or nxt not in role_ids()):
            out.append(f"warning: {where}: handoff note {i}: next {nxt!r} is not a role")
        if "status" in note and note["status"] not in SPEC:
            out.append(f"warning: {where}: handoff note {i}: status {note['status']!r} is not a Spec status ({', '.join(SPEC)})")
    return out
