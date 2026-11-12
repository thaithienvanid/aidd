"""Settings files with comments, read and edited in place, for the harnesses whose own documentation says the file takes them.

JSONC is JSON with `//` and `/* */` comments, and trailing commas where the harness accepts them. A person keeps comments, key
order, indentation, line endings, and a byte order mark in such a file, so aidd never writes it whole. `patch` turns the text
the person keeps into the text that holds the new data, changing only the members and elements that differ and keeping every
other byte, and it refuses (ValueError) unless the result reads back as exactly the new data.

The syntaxes, by what the harness documents: `json` (strict), `comments` (comments, no trailing comma), and `jsonc` (both).
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field

BOM = "﻿"
_WS = re.compile(r"[ \t\r\n]*")
_INDENT = re.compile(r"[ \t]*")


def _comment_spans(text: str) -> list[tuple[int, int]]:
    """Each comment in `text` as (start, end), outside strings. Raises ValueError for a string or a comment that never closes."""
    spans, i, n = [], 0, len(text)
    while i < n:
        if text[i] == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
            if i >= n:
                raise ValueError("a string is not closed")
            i += 1
        elif text.startswith("//", i):
            end = next((j for j in range(i, n) if text[j] in "\r\n"), n)
            spans.append((i, end))
            i = end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                raise ValueError("a comment is not closed")
            spans.append((i, end + 2))
            i = end + 2
        else:
            i += 1
    return spans


def _clean(text: str, syntax: str) -> str:
    """`text` as strict JSON with every character in place: each comment is spaces (its line breaks stay), and with `jsonc`
    each trailing comma is a space, so a position in the result is a position in `text`."""
    chars = list(text)
    for start, end in _comment_spans(text):
        for k in range(start, end):
            if chars[k] not in "\r\n":
                chars[k] = " "
    blank = "".join(chars)
    if syntax != "jsonc":
        return blank
    i = 0
    while i < len(blank):
        if blank[i] == '"':
            i = _string_end(blank, i)
            continue
        if blank[i] == "," and (j := _skip(blank, i + 1)) < len(blank) and blank[j] in "}]":
            chars[i] = " "
        i += 1
    return "".join(chars)


def has_comments(text: str) -> bool:
    """Whether a file holds a comment, which a person wrote and aidd never deletes."""
    try:
        return bool(_comment_spans(text))
    except ValueError:
        return False


def loads(text: str, syntax: str = "jsonc") -> object:
    """The data in a settings file's text, as its harness reads `syntax`. Raises ValueError, naming the line and column. With
    comments allowed, empty text, or text that is only comments, is no data at all: `{}`, as an editor reads an empty
    settings file; strict JSON refuses it."""
    body = text.removeprefix(BOM)
    clean = _clean(body, syntax) if syntax != "json" else body
    if not clean.strip() and syntax != "json":
        return {}
    return json.loads(clean)


@dataclass
class _Item:
    """A member of an object (`key` set) or an element of an array, with the spans in the text."""

    key: str | None
    start: int
    node: _Node
    comma: int | None = None  # where the comma after it sits, when there is one


@dataclass
class _Node:
    start: int
    end: int
    kind: str  # object, array, or scalar
    items: list[_Item] = field(default_factory=list)


def _skip(s: str, i: int) -> int:
    return _WS.match(s, i).end()  # type: ignore[union-attr]


def _string_end(s: str, i: int) -> int:
    i += 1
    while s[i] != '"':
        i += 2 if s[i] == "\\" else 1
    return i + 1


def _parse(s: str, i: int) -> _Node:
    """The value at `i` in cleaned text, as spans: every container with its members or elements."""
    i = _skip(s, i)
    if s[i] not in "{[":
        end = _string_end(s, i) if s[i] == '"' else next((j for j in range(i, len(s)) if s[j] in ",}] \t\r\n"), len(s))
        return _Node(i, end, "scalar")
    close = "}" if s[i] == "{" else "]"
    node, j = _Node(i, 0, "object" if close == "}" else "array"), i + 1
    while True:
        j = _skip(s, j)
        if s[j] == close:
            node.end = j + 1
            return node
        start, key = j, None
        if close == "}":
            key_end = _string_end(s, j)
            key, j = json.loads(s[j:key_end]), _skip(s, _skip(s, key_end) + 1)
        item = _Item(key, start, _parse(s, j))
        j = _skip(s, item.node.end)
        if s[j] == ",":
            item.comma, j = j, j + 1
        node.items.append(item)


def _unit(text: str) -> str:
    """The indentation one level adds in `text`: its first indented line's own, two spaces when none is indented."""
    m = re.search(r"^([ \t]+)\S", text, re.M)
    return m.group(1) if m else "  "


def _render(value: object, unit: str, indent: str, nl: str) -> str:
    """A new value as text: an object one member to a line, an array one element to a line (an object in it on one line)."""
    inner = indent + unit
    if isinstance(value, dict) and value:
        return "{" + nl + ("," + nl).join(f"{inner}{json.dumps(k)}: {_render(v, unit, inner, nl)}" for k, v in value.items()) + nl + indent + "}"
    if isinstance(value, list) and value:
        return "[" + nl + ("," + nl).join(inner + json.dumps(v) for v in value) + nl + indent + "]"
    return json.dumps(value)


@dataclass
class _Layout:
    text: str
    unit: str
    nl: str


def _rebuild(lay: _Layout, node: _Node, plan: list[tuple[_Item | None, str]]) -> str:
    """A container with the members or elements in `plan`, in order: (the old item and its new text, or None and a new
    member's text). New members after the last old one go after the comments that end the container, on lines of their own,
    and the comments of an item left out stay, after the last one, so no comment is lost or moved onto aidd's lines."""
    text, items = lay.text, node.items
    close = node.end - 1
    lead, prev = {}, node.start + 1
    for it in items:
        lead[id(it)] = text[prev : it.start]
        prev = it.comma + 1 if it.comma is not None else it.node.end
    tail = text[prev:close]
    parent = _INDENT.match(text, text.rfind("\n", 0, node.start) + 1).group()  # type: ignore[union-attr]
    first = lead[id(items[0])] if items else ""
    multiline = not items or "\n" in first + tail
    indent = first.rsplit("\n", 1)[-1] if "\n" in first else parent + lay.unit
    pieces = []
    for old, new in plan:
        if old is None:
            pieces.append((lay.nl + indent if multiline else " ") + new)
        else:
            pieces.append(lead[id(old)] + new + (text[old.node.end : old.comma] if old.comma is not None else ""))
    last_old = max((i for i, (old, _) in enumerate(plan) if old is not None), default=-1)
    head, appended = pieces[: last_old + 1], pieces[last_old + 1 :]
    kept = {id(old) for old, _ in plan if old is not None}
    carried = []
    for it in items:
        if id(it) not in kept:
            end = it.comma if it.comma is not None else it.node.end
            gone = lead[id(it)] + text[it.start : end]
            carried += [(gone[a:b], "\n" not in gone[:a]) for a, b in _comment_spans(gone)]  # (the comment, on its neighbour's line)
    extra = "".join((" " if beside or not multiline else lay.nl + indent) + c for c, beside in carried)
    trailing = bool(items) and items[-1].comma is not None
    open_, shut = text[node.start], text[close]
    if not appended:
        if carried and carried[-1][0].startswith("//") and not tail.lstrip(" \t").startswith(("\n", "\r")):
            extra += lay.nl
        return open_ + ",".join(head) + ("," if trailing and head else "") + extra + ("" if not pieces and not carried else tail) + shut
    cut = tail.rfind("\n")
    if multiline and cut >= 0 and not tail[cut:].strip():
        body, closing = tail[: cut - 1 if tail[cut - 1 : cut] == "\r" else cut], tail[cut - 1 if tail[cut - 1 : cut] == "\r" else cut :]
    elif multiline and not tail.strip():
        body, closing = "", lay.nl + parent
    else:
        body, closing = tail, ""
    return open_ + ",".join(head) + ("," if head else "") + extra + body + ",".join(appended) + ("," if trailing else "") + closing + shut


def _canon(value: object) -> str:
    return json.dumps(value, sort_keys=True)


def _edit(lay: _Layout, node: _Node, old: object, new: object) -> str:
    """The text of `node`, whose value is `old`, once it holds `new`: untouched when they are equal, else the container's
    differing members or elements rebuilt, and any other value replaced."""
    text = lay.text
    if old == new:
        return text[node.start : node.end]
    if node.kind == "object" and isinstance(old, dict) and isinstance(new, dict):
        keys = [it.key for it in node.items]
        if len(set(keys)) != len(keys):
            raise ValueError("it names a key twice")
        parent = _INDENT.match(text, text.rfind("\n", 0, node.start) + 1).group()  # type: ignore[union-attr]
        plan: list[tuple[_Item | None, str]] = [
            (it, _item_text(lay, it, _edit(lay, it.node, old.get(it.key), new[it.key]))) for it in node.items if it.key in new
        ]
        indent = parent + lay.unit
        plan += [(None, f"{json.dumps(k)}: {_render(new[k], lay.unit, indent, lay.nl)}") for k in new if k not in old]
        return _rebuild(lay, node, plan)
    if node.kind == "array" and isinstance(old, list) and isinstance(new, list):
        parent = _INDENT.match(text, text.rfind("\n", 0, node.start) + 1).group()  # type: ignore[union-attr]
        plan = []
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, [_canon(x) for x in old], [_canon(x) for x in new], autojunk=False).get_opcodes():
            if tag == "equal":
                plan += [(node.items[i], _item_text(lay, node.items[i], text[node.items[i].node.start : node.items[i].node.end])) for i in range(i1, i2)]
            plan += [(None, _render(v, lay.unit, parent + lay.unit, lay.nl)) for v in new[j1:j2]] if tag in ("insert", "replace") else []
        return _rebuild(lay, node, plan)
    return _render(new, lay.unit, _INDENT.match(text, text.rfind("\n", 0, node.start) + 1).group(), lay.nl)  # type: ignore[union-attr]


def _item_text(lay: _Layout, it: _Item, value_text: str) -> str:
    """A member or element as it reads with its value `value_text`: the key and what sits before the value, as they were."""
    return lay.text[it.start : it.node.start] + value_text


def patch(text: str, old: dict, new: dict, syntax: str) -> str:
    """`text`, which holds `old`, as it reads once it holds `new`. Raises ValueError when the edit cannot be proven: the
    result must read back, as `syntax`, as exactly `new`. Comments, other settings, key order, indentation, line endings,
    and a byte order mark stay."""
    bom, body = (BOM if text.startswith(BOM) else ""), text.removeprefix(BOM)
    nl = "\r\n" if "\r\n" in body else "\n"
    lay = _Layout(body, _unit(body), nl)
    clean = _clean(body, "comments")  # comments only: the trailing commas stay, so the parser finds where each one sits
    if not clean.strip():  # empty, or only comments: the object goes after them
        out = body + ("" if not body or body.endswith("\n") else nl) + _render(new, lay.unit, "", nl) + nl
    else:
        root = _parse(clean, 0)
        out = body[: root.start] + _edit(lay, root, old, new) + body[root.end :]
    try:
        back = loads(out, syntax)
    except ValueError as exc:
        raise ValueError(f"the edited text does not read back ({exc})") from exc
    if back != new:
        raise ValueError("the edited text does not read back as the new settings")
    return bom + out
