"""The handoff note: the `aidd-handoff` block a role ends each run with, the latest one a document holds, and what it asks a person for."""

from __future__ import annotations

import collections
import functools
import re
import unicodedata

from aidd import config
from aidd.kernel import documents, json_schema, resources, strict_yaml
from aidd.workitems import commit_text

# Approvals that a handoff note must not name as its `next_role`. The Approver inbox follows the derived status, so a note
# names the role that takes the work, and `aidd validate` warns about one of these.
APPROVAL_STEPS = ("spec.approve", "pr.merge", "intent.approve", "product_scope.approve")
HANDOFF_SCHEMA = "handoff.schema.json"
HANDOFF_FENCE = re.compile(r"^```aidd-handoff[ \t]*\r?\n(.*?)^```[ \t]*$", re.S | re.M)


@functools.cache
def handoff_keys() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The note's required keys and its optional keys, as schemas/handoff.schema.json lists them: its one owner."""
    schema = resources.load_json(HANDOFF_SCHEMA)
    required = tuple(schema["required"])
    return required, tuple(k for k in schema["properties"] if k not in required)


@functools.cache
def stop_codes() -> tuple[str, ...]:
    """The codes a note's `stopped_at` starts with, as the common schema's `stop_code` lists them: its one owner."""
    return tuple(resources.load_json("common.schema.json")["$defs"]["stop_code"]["enum"])


def stop_code_problem(stopped_at: str) -> str | None:
    """What is wrong with a `stopped_at` that does not start with a stop code, with the fix; None when it does. The code
    stands alone, or `: ` and any detail follow it, such as `"ask: spec.approve SPEC-3"`."""
    if stopped_at.strip().partition(":")[0].rstrip() in stop_codes():
        return None
    return (
        f"stopped_at {documents.one_line(stopped_at)!r} does not start with a stop code. Start it with one of "
        f'{", ".join(stop_codes())}, then `: ` and any detail, quoted, such as `stopped_at: "ask: spec.approve SPEC-3"`. The aidd skill\'s '
        "references/handoff.md says where each code comes from"
    )


def _canonical(key: object) -> str:
    """The key a misspelling stands for: lowercase, with `_` for a space, and `next` (the old name) as `next_role`."""
    spelled = str(key).casefold().replace(" ", "_")
    return "next_role" if spelled == "next" else spelled


def unknown_key_fix(key: str, known: tuple[str, ...]) -> str:
    """An unknown key of a note, with its fix: the known key it misspells by case, spaces, or its old name `next`, or remove
    it and say it in a known one."""
    same = next((k for k in known if k.casefold() == _canonical(key)), None)
    return f"{key} (write it as `{same}`)" if same else f"{key} (remove it, or put what it says in `done`, `needs`, or `decided`)"


@functools.cache
def role_ids() -> frozenset[str]:
    return frozenset(resources.load_json("roles.json")["roles"])


def handoff_blocks(text: str) -> list[tuple[str, dict | None, str]]:
    """Every ```aidd-handoff block in a document, in order and in one pass of the fence pattern: (its text, its YAML as
    a dict or None, and the parse error)."""
    out: list[tuple[str, dict | None, str]] = []
    for m in HANDOFF_FENCE.finditer(text):
        raw = m.group(1)
        try:
            # The error names the document's own line, so a person opens it there.
            out.append((raw, documents.parse_yaml(raw, "aidd-handoff block", first_line=text.count("\n", 0, m.start(1)) + 1), ""))
        except documents.DocumentError as exc:
            out.append((raw, None, str(exc)))
    return out


# An entry's `id`, as the common schema's `id` pattern, its one owner, gives it.
ENTRY_ID = re.compile(resources.load_json("common.schema.json")["$defs"]["id"]["pattern"])


def _choices(entry: dict) -> list[str]:
    """The choices an entry offers, each a string, in its order."""
    options = entry.get("options")
    return [o["choice"] for o in options if isinstance(o, dict) and isinstance(o.get("choice"), str)] if isinstance(options, list) else []


def _note_answers(note: dict) -> dict[str, str]:
    """The answers a note's `answered` gives, by entry id: one choice each. An item that does not read, and an id the note
    answers twice with different choices, answer nothing."""
    items = note.get("answered")
    given: dict[str, set[str]] = {}
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("choice"), str):
            given.setdefault(item["id"], set()).add(item["choice"])
    return {i: next(iter(c)) for i, c in given.items() if len(c) == 1}


def _names(text: object, ident: str) -> bool:
    """Whether `text`, a note's `needs`, names the entry id `ident` as a word of its own."""
    return isinstance(text, str) and bool(re.search(rf"(?<![A-Za-z0-9_-]){re.escape(ident)}(?![A-Za-z0-9_-])", text))


def _entry_problem(entry: object, ids: list[object]) -> str:
    """Why an entry cannot be answered, or "": an `id` that is missing, not an id, or used twice in its note, no `what`, or
    fewer than two choices that differ. `ids` holds the id of each entry of the note."""
    if not isinstance(entry, dict):
        return " is not an entry with an `id`, a `what`, and `options`"
    ident, what = entry.get("id"), entry.get("what")
    shown = f" ({documents.one_line(what, 80)!r})" if isinstance(what, str) else ""
    if not isinstance(ident, str) or not ENTRY_ID.match(ident):
        return f"{shown} has no `id`: add a short one to it, such as `no-tests-check`, in that note"
    if ids.count(ident) > 1:
        return f" `{ident}` shares its `id` with another entry of the note: give each its own"
    if not isinstance(what, str) or not what.strip():
        return f" `{ident}` has no `what`"
    choices = _choices(entry)
    if len(choices) < 2 or len(set(choices)) < len(choices):
        return f" `{ident}` offers fewer than two choices that differ"
    return ""


def decision_states(blocks: list[tuple[str, dict | None, str]]) -> tuple[list[dict], list[str]]:
    """Each `open_decisions` entry that reads, as {entry, status, choice}, and why each other entry cannot be read, in the
    notes' order, from blocks as `handoff_blocks` gives them. An entry is `answered` when a later note's `answered` holds its
    `id` and one of its own `options[].choice`, written exactly; `needs_person` when it is not and a later note's `needs` names
    its id; else `open`. One `answered` item clears one entry: the newest still open before its note that has that `id` and
    offers that choice, so two entries that share an id need two answers. A note's `decided` text answers nothing, since a
    match of prose is no fact. An entry is an agent's text, so it can only add to what stays open: an entry with no usable
    `id`, a duplicate `id` in one note, a field that is no list, and a note that names the field and does not parse each stay
    open until the note is fixed. A field left empty asks nothing."""
    notes = [note if isinstance(note, dict) else None for _, note, _ in blocks]
    held: list[tuple[int, dict]] = []  # each entry that reads, with the index of its note, in the notes' order
    unreadable: list[str] = []
    for i, (raw, _note, _err) in enumerate(blocks):
        note = notes[i]
        if note is None:
            if "open_decisions" in raw:
                unreadable.append(f"handoff note {i + 1} names open_decisions and does not read as a note")
            continue
        entries = note.get("open_decisions")
        if entries is None or entries == []:
            continue
        if not isinstance(entries, list):
            unreadable.append(f"handoff note {i + 1}'s open_decisions is not a list")
            continue
        ids = [e.get("id") if isinstance(e, dict) else None for e in entries]
        for k, entry in enumerate(entries, 1):
            if problem := _entry_problem(entry, ids):
                unreadable.append(f"entry {k} of handoff note {i + 1}{problem}")
            else:
                held.append((i, entry))
    taken: dict[int, str] = {}  # the position in `held` of each answered entry, and the choice
    for j, note in enumerate(notes):
        for ident, choice in (_note_answers(note) if note else {}).items():
            open_before = [n for n, (i, e) in enumerate(held) if i < j and e["id"] == ident and n not in taken and choice in _choices(e)]
            if open_before:
                taken[open_before[-1]] = choice
    states: list[dict] = []
    for n, (i, entry) in enumerate(held):
        if n in taken:
            states.append({"entry": entry, "status": "answered", "choice": taken[n]})
            continue
        waits = any(_names(m.get("needs"), entry["id"]) for m in notes[i + 1 :] if m is not None)
        states.append({"entry": entry, "status": "needs_person" if waits else "open"})
    return states, unreadable


def decision_warnings(where: str, blocks: list[tuple[str, dict | None, str]]) -> list[str]:
    """`aidd validate` warnings for the answers in one file's notes, so a lead learns at write time what the delegate check
    would hold open: an `id` used twice among a note's entries or in several notes, an answer in the note that holds its entry or an earlier one,
    and an answer whose choice the entry, in an earlier note of the same file, does not offer. An answer to an entry the file
    does not hold may answer one in another text, such as the PR/MR's body, so it is not warned about."""
    held: list[tuple[int, str, list[str]]] = []  # each entry with an id: its note, its id, and its choices
    given: list[tuple[int, str, object]] = []  # each answer with an id: its note, the id, and the choice
    for i, (_raw, note, _err) in enumerate(blocks, 1):
        if not isinstance(note, dict):
            continue
        entries = note.get("open_decisions")
        held += [(i, e["id"], _choices(e)) for e in entries if isinstance(e, dict) and isinstance(e.get("id"), str)] if isinstance(entries, list) else []
        answers = note.get("answered")
        given += [(i, a["id"], a.get("choice")) for a in answers if isinstance(a, dict) and isinstance(a.get("id"), str)] if isinstance(answers, list) else []
    out: list[str] = []
    for (i, ident), count in collections.Counter((i, x) for i, x, _ in held).items():
        if count > 1:
            out.append(f"warning: {where}: handoff note {i}: two open_decisions entries have the id `{ident}`. Give each its own id")
    for ident in dict.fromkeys(x for _, x, _ in held):
        notes_with = sorted({i for i, x, _ in held if x == ident})
        if len(notes_with) > 1:
            out.append(
                f"warning: {where}: open_decisions entries in notes {', '.join(map(str, notes_with))} share the id `{ident}`: give each decision its own id, so one answer clears one decision"
            )
    for i, ident, choice in given:
        before = [(j, c) for j, x, c in held if x == ident and j < i]
        if any(j >= i for j, x, _ in held if x == ident) and not before:
            out.append(f"warning: {where}: handoff note {i} answers `{ident}`, which its own note or a later one holds. Answer it on a note after the entry")
        elif before and not any(choice in c for _, c in before):
            offered = ", ".join(f"`{c}`" for c in before[-1][1])
            out.append(
                f"warning: {where}: handoff note {i} answers `{ident}` with {documents.one_line(str(choice), 80)!r}, which note "
                f"{before[-1][0]} does not offer. Write one of {offered} exactly"
            )
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
    breaks schemas/handoff.schema.json, a `next_role` that is not a role (an approval is not a role: the person decides it),
    an unknown `status`, an agent's `by` not spelled `agent:<harness id>/<model>` or naming a role, hidden characters, text posing as a
    person's words, or an open decision's answer the delegate check would not count (`decision_warnings`). They advise and block nothing."""
    from aidd.workitems.status import SPEC_STATUSES

    required, optional = handoff_keys()
    out = []
    blocks = handoff_blocks(text)
    for i, (raw, note, err) in enumerate(blocks, 1):
        out += _text_warnings(where, i, raw, note)
        if note is None:
            out.append(f"warning: {where}: handoff note {i} is not YAML ({err.split(': ', 1)[-1]})")
            continue
        # A key in the wrong case is one finding: unknown, with the spelling to write, never missing too.
        missing = [k for k in required if k not in note and k not in {_canonical(n) for n in note}]
        unknown = [unknown_key_fix(k, required + optional) for k in sorted(set(note) - set(required) - set(optional), key=str)]
        if missing:
            out.append(
                f"warning: {where}: handoff note {i} has no {', '.join(missing)}. Add {'each' if len(missing) > 1 else 'it'}, as the aidd skill's "
                "references/handoff.md shows; `needs` and `stopped_at` take `none` when nothing applies"
            )
        if unknown:
            out.append(f"warning: {where}: handoff note {i} has keys aidd does not read: {'; '.join(documents.one_line(k) for k in unknown)}")
        # The schema also types each value. `next_role`, `status`, and an agent's `by` have the messages below, and a missing or
        # unknown key the messages above, so only a value's own type error (`$.done: expected string`) is added here.
        by = note.get("by")
        agent = isinstance(by, str) and by.startswith("agent:")
        for e in json_schema.validate(note, HANDOFF_SCHEMA):
            if e.startswith("$.") and not e.startswith(("$.next_role", "$.status", *(("$.by",) if agent else ()))):
                out.append(f"warning: {where}: handoff note {i}: {e[2:]}")
        nxt = note.get("next_role")
        if nxt in APPROVAL_STEPS:
            out.append(
                f"warning: {where}: handoff note {i}: next_role {nxt!r} is an approval, not a role. aidd puts the Spec in the Approver "
                "inbox from its derived status. Name the role that takes the work next"
            )
        elif "next_role" in note and (not isinstance(nxt, str) or nxt not in role_ids()):
            out.append(f"warning: {where}: handoff note {i}: next_role {nxt!r} is not a role")
        if agent and (fix := commit_text.assisted_by_fix(str(by)[6:])):
            out.append(
                f"warning: {where}: handoff note {i}: by `{documents.one_line(by)}` is not `agent:<harness id>/<model>`; write `by: agent:{fix}`.{commit_text.harness_ids_note(str(by)[6:])}"
            )
        if config.typed_identity(by)[0] == "role":
            out.append(
                f"warning: {where}: handoff note {i}: by `{documents.one_line(by)}` names a role, not who ran it; write `by: agent:<harness id>/<model>`, as the commits' `Assisted-by` names it"
            )
        if "status" in note and note["status"] not in SPEC_STATUSES:
            out.append(
                f"warning: {where}: handoff note {i}: status {note['status']!r} is not a Spec status ({', '.join(SPEC_STATUSES)}): write one of them, or leave `status` out"
            )
        if isinstance(note.get("stopped_at"), str) and (problem := stop_code_problem(note["stopped_at"])):
            out.append(f"warning: {where}: handoff note {i}: {problem}")
    return out + decision_warnings(where, blocks)
