"""YAML in a strict subset: what aidd reads from front matter and its config, and what it writes there.

The subset has one meaning in every YAML reader, YAML 1.1 and 1.2 alike, so the gate and a person's editor never read
the same file two ways. Anything outside it is an error that names the line, never a guess:

- Block mappings and block sequences, indented with spaces; flow sequences `[a, b]` and flow mappings `{a: 1}`, which
  may run over several lines.
- Strings: double-quoted (the JSON escapes), single-quoted (`''` is a quote), a literal block (`|` or `|-`), or plain
  text that cannot be read as anything else. A plain value that YAML could read as a number, a date, a boolean, or null
  (`1.0.0`, `2026-10-07`, `yes`, `on`, `~`) must be quoted.
- Integers, decimals such as `1.5`, and `true` or `false`.
- Keys are plain names (a letter or `_`, then letters, digits, `_`, `-`, or `.`), or double-quoted, such as
  `"baseline:auth"`. A key appears once in its mapping.
- Not in the subset: null, anchors and aliases, tags, merge keys, complex keys, several documents, tabs in indentation.
"""

from __future__ import annotations

import json
import re
from typing import Any

# The deepest nesting of mappings and sequences: far past any real document, and far short of a stack overflow.
MAX_DEPTH = 32

KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")
_INT = re.compile(r"-?(?:0|[1-9][0-9]*)")
_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)\.[0-9]+")
# Words some YAML reader takes as a boolean or null, in any case: a plain value or a key must not be one of them.
_RESERVED = frozenset({"y", "n", "yes", "no", "on", "off", "true", "false", "null", "~", "nan", ".nan", "inf", ".inf", "-.inf"})
# Plain text that every YAML reader takes as the same string: it starts with a letter, `_`, `/`, a `-` before a letter
# (a command's flag, `-q`), or a `.` before a letter (`.github/`); it holds no `#`, no `?`, no flow indicator (`[]{},`), and no
# `: `; and no quote follows a space or a colon, where a reader could take it as the start of a quoted value.
_PLAIN = re.compile(r"(?:[A-Za-z_/\u00c0-\uffff]|-[-A-Za-z]|\.[A-Za-z_/])[^\x00-\x1f\x7f#\[\]{},?]*")
# In block style a plain value may also hold `,`, brackets, and a `#` that no space comes before (`C#`): only inside a
# flow collection do they end the value.
_PLAIN_BLOCK = re.compile(r"(?:[A-Za-z_/\u00c0-\uffff]|-[-A-Za-z]|\.[A-Za-z_/])[^\x00-\x1f\x7f?]*")
_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
# Characters a YAML reader takes as a line break (NEL, LS, PS), refuses (C1 controls, non-characters, lone surrogates),
# or may drop (a byte order mark past the start): none may appear anywhere, quoted or not.
_UNREADABLE = re.compile(r"[\x7f-\x9f\u2028\u2029\ufeff\ufffe\uffff\ud800-\udfff]")


class YamlError(ValueError):
    """YAML outside the subset. `line` is 1-based, counted from the first line of the text read."""

    def __init__(self, line: int, message: str) -> None:
        super().__init__(f"line {line}: {message}")
        self.line = line


class _Line:
    __slots__ = ("indent", "number", "raw", "text")

    def __init__(self, number: int, indent: int, text: str, raw: str) -> None:
        self.number, self.indent, self.text, self.raw = number, indent, text, raw


def _strip_comment(s: str, number: int) -> str:
    """`s` without its comment: a `#` at the start or after a space, outside quotes. A quote left open is an error."""
    quote = ""
    i = 0
    while i < len(s):
        c = s[i]
        if quote == '"':
            if c == "\\":
                i += 1
            elif c == '"':
                quote = ""
        elif quote == "'":
            if c == "'":
                if s[i + 1 : i + 2] == "'":
                    i += 1
                else:
                    quote = ""
        elif c in "\"'" and (i == 0 or s[i - 1] in " [{,:"):
            quote = c
        elif c == "#" and (i == 0 or s[i - 1] == " "):
            return s[:i].rstrip(" ")
        i += 1
    if quote:
        raise YamlError(number, "a quoted value does not end on its line; close the quote")
    return s.rstrip(" ")


def _lines(text: str) -> list[_Line]:
    out = []
    for number, raw in enumerate(text.split("\n"), 1):
        stripped = raw.lstrip(" ")
        if stripped.startswith("\t"):
            raise YamlError(number, "a tab in the indentation; indent with spaces")
        out.append(_Line(number, len(raw) - len(stripped), stripped, raw))
    return out


def _key_at(s: str, i: int, number: int) -> tuple[str, int] | None:
    """The key that starts at `s[i]`, plain or double-quoted, and where it ends; None when no key starts there."""
    if s[i : i + 1] == '"':
        flow = _Flow(s, number)
        flow.i = i
        return flow.double(), flow.i
    m = KEY.match(s, i)
    return (m.group(0), m.end()) if m else None


def _key_line(text: str, number: int) -> tuple[str, str] | None:
    """`key: value` (or `key:` alone) as (key, value text); None when the text is not one."""
    found = _key_at(text, 0, number)
    if found is None:
        return None
    name, end = found
    if text[end : end + 1] != ":" or text[end + 1 : end + 2] not in ("", " "):
        return None
    _check_key(name, number, quoted=text[0] == '"')
    return name, text[end + 1 :].strip(" ")


def _check_key(key: str, number: int, quoted: bool = False) -> None:
    if quoted:
        if not key:
            raise YamlError(number, 'an empty key ""; name the key')
        return
    if key.lower() in _RESERVED:
        raise YamlError(number, f"`{key}` cannot be a key: some YAML readers take it as a boolean or null")


def _plain(s: str, number: int, in_flow: bool = True) -> Any:
    if s in ("true", "false"):
        return s == "true"
    if _INT.fullmatch(s):
        return int(s)
    if _DECIMAL.fullmatch(s):
        return float(s)
    if (
        s.lower() in _RESERVED
        or not (_PLAIN if in_flow else _PLAIN_BLOCK).fullmatch(s)
        or " #" in s
        or ": " in s
        or s.endswith((":", " "))
        or re.search(r"""[ :]['"]""", s)  # where a quote may open, so a reader could take it as one
    ):
        raise YamlError(number, f"put this value in double quotes: {s}")
    return s


class _Flow:
    """A value on one logical line: a scalar, or a flow sequence or mapping (which may come from several lines)."""

    def __init__(self, s: str, number: int) -> None:
        self.s, self.i, self.number = s, 0, number

    def error(self, message: str) -> YamlError:
        return YamlError(self.number, message)

    def ws(self) -> None:
        while self.i < len(self.s) and self.s[self.i] in " \n":
            self.i += 1

    def value(self, depth: int, in_flow: bool) -> Any:
        if depth > MAX_DEPTH:
            raise self.error(f"mappings and sequences nest more than {MAX_DEPTH} deep")
        self.ws()
        if self.i >= len(self.s):
            raise self.error("a value is missing")
        c = self.s[self.i]
        if c == "[":
            return self.sequence(depth)
        if c == "{":
            return self.mapping(depth)
        if c == '"':
            return self.double()
        if c == "'":
            return self.single()
        if c in "&*!|>%@`?:,]}#":
            raise self.error(f"a value cannot start with `{c}` here; put it in double quotes")
        start = self.i
        stops = ",]}\n" if in_flow else "\n"
        while self.i < len(self.s) and self.s[self.i] not in stops:
            self.i += 1
        return _plain(self.s[start : self.i].rstrip(" "), self.number, in_flow)

    def double(self) -> str:
        out: list[str] = []
        i = self.i + 1
        while i < len(self.s):
            c = self.s[i]
            if c == '"':
                self.i = i + 1
                return "".join(out)
            if c == "\n" or _CONTROL.match(c) or c == "\t":
                break
            if c == "\\":
                e = self.s[i + 1 : i + 2]
                if e in _ESCAPES:
                    out.append(_ESCAPES[e])
                    i += 2
                    continue
                if e == "u" and re.fullmatch(r"[0-9a-fA-F]{4}", self.s[i + 2 : i + 6]):
                    code = int(self.s[i + 2 : i + 6], 16)
                    if 0xD800 <= code <= 0xDFFF:
                        raise self.error("a \\u escape names half of a surrogate pair; write the character itself")
                    out.append(chr(code))
                    i += 6
                    continue
                raise self.error(f'`\\{e}` is not an escape aidd reads; use \\\\, \\", \\n, \\t, or \\uXXXX')
            out.append(c)
            i += 1
        raise self.error("a double-quoted value does not end on its line, or holds a raw tab or control character")

    def single(self) -> str:
        out: list[str] = []
        i = self.i + 1
        while i < len(self.s):
            c = self.s[i]
            if c == "'":
                if self.s[i + 1 : i + 2] == "'":
                    out.append("'")
                    i += 2
                    continue
                self.i = i + 1
                return "".join(out)
            if c == "\n" or _CONTROL.match(c) or c == "\t":
                break
            out.append(c)
            i += 1
        raise self.error("a single-quoted value does not end on its line, or holds a raw tab or control character")

    def sequence(self, depth: int) -> list:
        self.i += 1
        items: list = []
        while True:
            self.ws()
            if self.s[self.i : self.i + 1] == "]":
                self.i += 1
                return items
            items.append(self.value(depth + 1, True))
            self.ws()
            c = self.s[self.i : self.i + 1]
            if c == ",":
                self.i += 1
            elif c != "]":
                raise self.error("a sequence needs `,` between its items and `]` at its end")

    def mapping(self, depth: int) -> dict:
        self.i += 1
        out: dict = {}
        while True:
            self.ws()
            if self.s[self.i : self.i + 1] == "}":
                self.i += 1
                return out
            found = _key_at(self.s, self.i, self.number)
            if not found or self.s[found[1] : found[1] + 2] != ": ":
                raise self.error("a mapping entry is `key: value`, with a plain or double-quoted key and a space after the colon")
            key, end = found
            _check_key(key, self.number, quoted=self.s[self.i] == '"')
            if key in out:
                raise self.error(f"`{key}` appears twice in one mapping")
            self.i = end + 2
            out[key] = self.value(depth + 1, True)
            self.ws()
            c = self.s[self.i : self.i + 1]
            if c == ",":
                self.i += 1
            elif c != "}":
                raise self.error("a mapping needs `,` between its entries and `}` at its end")


def _opens(s: str) -> int:
    """How many `[` and `{` stay open at the end of `s`, quotes skipped."""
    depth, quote, i = 0, "", 0
    while i < len(s):
        c = s[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 1
            elif c == quote:
                quote = ""
        elif c in "\"'" and (i == 0 or s[i - 1] in " \n[{,:"):
            quote = c
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
        i += 1
    return depth


def _is_item(text: str) -> bool:
    return text == "-" or text.startswith("- ")


class _Parser:
    def __init__(self, text: str) -> None:
        self.lines = _lines(text)
        self.i = 0

    def current(self) -> _Line | None:
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if _strip_comment(line.text, line.number):
                return line
            self.i += 1
        return None

    def block(self, indent: int, depth: int) -> Any:
        line = self.current()
        assert line is not None
        if depth > MAX_DEPTH:
            raise YamlError(line.number, f"mappings and sequences nest more than {MAX_DEPTH} deep")
        if _is_item(_strip_comment(line.text, line.number)):
            return self.sequence(indent, depth)
        return self.mapping(indent, depth)

    def inline(self, rest: str, line: _Line, depth: int) -> Any:
        """A value that starts on `line` after its key or dash; a flow collection may continue on deeper lines."""
        if rest in ("|", "|-"):
            return self.literal(line, keep=rest == "|")
        parts = [rest]
        while rest[:1] in "[{" and _opens("\n".join(parts)) > 0:
            self.i += 1
            nxt = self.current()
            if nxt is None or nxt.indent <= line.indent:
                raise YamlError(line.number, "a `[` or `{` is not closed")
            parts.append(_strip_comment(nxt.text, nxt.number))
        flow = _Flow("\n".join(parts), line.number)
        value = flow.value(depth, False)
        flow.ws()
        if flow.i != len(flow.s):
            raise YamlError(line.number, f"unexpected text after the value: {flow.s[flow.i :].strip()}")
        self.i += 1
        return value

    def literal(self, line: _Line, keep: bool) -> str:
        self.i += 1
        body: list[str] = []
        indent = None
        while self.i < len(self.lines):
            nxt = self.lines[self.i]
            if nxt.text.strip() == "":
                body.append("")
                self.i += 1
                continue
            if nxt.indent <= line.indent:
                break
            if indent is None:
                indent = nxt.indent
            elif nxt.indent < indent:
                raise YamlError(nxt.number, "a line of the `|` block is indented less than its first line")
            body.append(nxt.raw[indent:])
            self.i += 1
        while body and body[-1] == "":
            body.pop()
        if not body:
            raise YamlError(line.number, 'a `|` block holds no text; write "" for an empty value')
        if any("\t" in b or _CONTROL.search(b) or b != b.rstrip(" ") for b in body):
            raise YamlError(line.number, "a `|` block holds a tab, a control character, or a space at the end of a line")
        return "\n".join(body) + ("\n" if keep else "")

    def mapping(self, indent: int, depth: int) -> dict:
        out: dict = {}
        while (line := self.current()) is not None and line.indent >= indent:
            if line.indent > indent:
                raise YamlError(line.number, "this line is indented more than the lines around it")
            text = _strip_comment(line.text, line.number)
            if _is_item(text):
                raise YamlError(line.number, "a sequence item where a `key: value` line belongs")
            found = _key_line(text, line.number)
            if found is None:
                raise YamlError(line.number, "expected `key: value`, with a plain or double-quoted key and a space after the colon")
            key, rest = found
            if key in out:
                raise YamlError(line.number, f"`{key}` appears twice in one mapping")
            if rest:
                out[key] = self.inline(rest, line, depth + 1)
                continue
            self.i += 1
            nxt = self.current()
            if nxt is not None and nxt.indent > indent:
                out[key] = self.block(nxt.indent, depth + 1)
            elif nxt is not None and nxt.indent == indent and _is_item(_strip_comment(nxt.text, nxt.number)):
                out[key] = self.sequence(indent, depth + 1)
            else:
                raise YamlError(line.number, f'`{key}` has no value; write one, or [], {{}}, or "" for an empty one')
        return out

    def sequence(self, indent: int, depth: int) -> list:
        items: list = []
        while (line := self.current()) is not None and line.indent >= indent:
            if line.indent > indent:
                raise YamlError(line.number, "this line is indented more than the lines around it")
            text = _strip_comment(line.text, line.number)
            if not _is_item(text):
                break
            rest = text[1:].lstrip(" ")
            column = indent + (len(text) - len(rest))
            if not rest:
                self.i += 1
                nxt = self.current()
                if nxt is None or nxt.indent <= indent:
                    raise YamlError(line.number, "a sequence item has no value")
                items.append(self.block(nxt.indent, depth + 1))
            elif _is_item(rest) or _key_line(rest, line.number) is not None:
                # `- key: value` or `- - item`: the rest of the line opens a block at its own column.
                self.lines[self.i] = _Line(line.number, column, line.text[column - indent :], line.raw)
                items.append(self.block(column, depth + 1))
            else:
                items.append(self.inline(rest, line, depth + 1))
        return items


def load(text: str) -> dict:
    """A YAML document in the subset, as JSON-shaped data: a mapping at the top. Anything else is a YamlError."""
    if "\r" in text:
        raise YamlError(text.count("\n", 0, text.index("\r")) + 1, "a carriage return; save the file with LF line endings")
    if m := _UNREADABLE.search(text):
        raise YamlError(
            text.count("\n", 0, m.start()) + 1,
            f"character U+{ord(m.group(0)):04X}: some YAML readers break a line there or refuse it; remove it",
        )
    parser = _Parser(text)
    first = parser.current()
    if first is None:
        return {}
    if first.indent:
        raise YamlError(first.number, "the first key is indented; start it at the left margin")
    if _strip_comment(first.text, first.number) in ("---", "..."):
        raise YamlError(first.number, "a document marker; aidd reads one document, with no `---` or `...` inside")
    value = parser.mapping(0, 1)
    rest = parser.current()
    if rest is not None:
        raise YamlError(rest.number, "unexpected line: is it indented too little, or a `---` too many?")
    return value


def is_plain(s: str) -> bool:
    """True when `s` reads back as the same string without quotes."""
    try:
        return isinstance(_plain(s, 0), str)
    except YamlError:
        return False


def scalar(value: Any) -> str:
    """One value as the subset writes it: plain when that reads back the same, else JSON's double-quoted form."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        text = repr(value)
        if not _DECIMAL.fullmatch(text):
            raise ValueError(f"{value!r} has no decimal form the subset reads; write it as a string")
        return text
    if isinstance(value, str):
        if is_plain(value) and not _UNREADABLE.search(value):
            return value
        return _UNREADABLE.sub(lambda m: f"\\u{ord(m.group(0)):04x}", json.dumps(value, ensure_ascii=False))
    raise TypeError(f"the subset has no form for {type(value).__name__}")


def key(name: str) -> str:
    """`name` as a key: plain when it is a plain name no reader takes as a boolean or null, else double-quoted."""
    if not isinstance(name, str) or not name:
        raise ValueError(f"{name!r} is not a key the subset writes")
    if KEY.fullmatch(name) and name.lower() not in _RESERVED:
        return name
    return _UNREADABLE.sub(lambda m: f"\\u{ord(m.group(0)):04x}", json.dumps(name, ensure_ascii=False))


def flow(value: Any) -> str:
    """A value on one line: a scalar, `[a, b]`, or `{key: value}`."""
    if isinstance(value, list):
        return "[" + ", ".join(flow(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{key(k)}: {flow(v)}" for k, v in value.items()) + "}"
    return scalar(value)


# A sequence of scalars at most this wide stays on one line; a wider one gets a line per item.
FLOW_WIDTH = 100


def _block_list(value: list) -> bool:
    return bool(value) and (any(isinstance(v, (dict, list)) for v in value) or len(flow(value)) > FLOW_WIDTH)


def dump_lines(data: dict, indent: int = 0) -> list[str]:
    """`data` as block YAML lines at `indent`."""
    pad = " " * indent
    out: list[str] = []
    for k, v in data.items():
        if isinstance(v, dict) and v:
            out.append(f"{pad}{key(k)}:")
            out.extend(dump_lines(v, indent + 2))
        elif isinstance(v, list) and _block_list(v):
            out.append(f"{pad}{key(k)}:")
            out.extend(_items(v, indent + 2))
        else:
            out.append(f"{pad}{key(k)}: {flow(v)}")
    return out


def _items(values: list, indent: int) -> list[str]:
    pad = " " * indent
    out: list[str] = []
    for v in values:
        if isinstance(v, dict) and v:
            inner = dump_lines(v, indent + 2)
            out.append(f"{pad}- {inner[0][indent + 2 :]}")
            out.extend(inner[1:])
        elif isinstance(v, list) and _block_list(v):
            inner = _items(v, indent + 2)
            out.append(f"{pad}- {inner[0][indent + 2 :]}")
            out.extend(inner[1:])
        else:
            out.append(f"{pad}- {flow(v)}")
    return out


def dump(data: dict) -> str:
    """`data` in the subset: block mappings, short sequences of scalars on one line, and every string that could read as
    something else quoted. `load(dump(d)) == d` for JSON-shaped `d` with no null."""
    return "\n".join(dump_lines(data)) + "\n" if data else ""


# Edits to YAML text that keep every comment and line a person wrote: the writers append items or set one entry, and
# then read the result again, so an edit that would not parse never reaches a file.


def item_lines(items: list, indent: int) -> list[str]:
    """`items` as block sequence lines at `indent`."""
    return _items(items, indent)


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _span(lines: list[str], name: str, start: int, end: int, indent: int) -> tuple[int, int] | None:
    """The lines of `name` as a key at `indent` within lines[start:end]: its own line, then every line below it that is
    blank, indented deeper, or a `- ` item at the same indent. Blank lines at the end are left out."""
    head = next((i for i in range(start, end) if lines[i].startswith(" " * indent + f"{name}:") and _indent_of(lines[i]) == indent
                 and re.match(rf"{re.escape(name)}:(?:[ ]|$)", lines[i][indent:])), None)  # fmt: skip
    if head is None:
        return None
    stop = head + 1
    while stop < end:
        ln = lines[stop]
        if ln.strip() and _indent_of(ln) <= indent and not (_indent_of(ln) == indent and _is_item(ln.strip())):
            break
        stop += 1
    while stop > head + 1 and not lines[stop - 1].strip():
        stop -= 1
    return head, stop


def _value_text(line: str, name: str, indent: int) -> str:
    return _strip_comment(line[indent + len(name) + 1 :], 0).strip(" ")


def _locate(lines: list[str], path: tuple[str, ...]) -> tuple[list[tuple[int, int, int]], int]:
    """The spans (head, stop, indent) of each key of `path` that exists, outermost first, and how many exist."""
    spans: list[tuple[int, int, int]] = []
    start, end, indent = 0, len(lines), 0
    for depth, name in enumerate(path):
        span = _span(lines, name, start, end, indent)
        if span is None:
            return spans, depth
        head, stop = span
        if depth < len(path) - 1 and _value_text(lines[head], name, indent):
            raise ValueError(f"`{'.'.join(path[: depth + 1])}` is written on one line; write it as a block to change what is inside it")
        spans.append((head, stop, indent))
        child = next((_indent_of(lines[i]) for i in range(head + 1, stop) if lines[i].strip() and not lines[i].strip().startswith("#")), indent + 2)
        start, end, indent = head + 1, stop, child
    return spans, len(path)


def _insert(lines: list[str], spans: list, found: int, path: tuple[str, ...], tail: list[str]) -> list[str]:
    """`lines` with the missing keys path[found:] created, holding `tail` (lines already indented for the last key)."""
    at, indent = (spans[-1][1], _child(lines, spans[-1])) if spans else (len(lines), 0)
    new = [" " * (indent + 2 * i) + f"{key(name)}:" for i, name in enumerate(path[found:])]
    shift = indent + 2 * len(new)
    block = new + [" " * shift + t if t.strip() else t for t in tail]
    if not spans and lines:
        block = ["", *block]
    return [*lines[:at], *block, *lines[at:]]


def _child(lines: list[str], span: tuple[int, int, int]) -> int:
    head, stop, indent = span
    return next((_indent_of(lines[i]) for i in range(head + 1, stop) if lines[i].strip() and not lines[i].strip().startswith("#")), indent + 2)


def _split(text: str) -> list[str]:
    return text.rstrip("\n").split("\n") if text.strip() else []


def append_items(text: str, path: str | tuple[str, ...], items: list, *, before: str = "", after: str = "") -> str:
    """`text` with `items` added at the end of the block sequence at `path` (a key, or keys from the top), which is
    created when missing, with an optional comment line `before` and `after` them. `[]` becomes a block; a sequence in
    flow style otherwise is a ValueError: aidd edits only block sequences."""
    path = (path,) if isinstance(path, str) else path
    lines = _split(text)
    spans, found = _locate(lines, path)

    def rendered(indent: int) -> list[str]:  # noqa: E306
        marks = lambda c: [" " * indent + c] if c else []  # noqa: E731
        return [*marks(before), *_items(items, indent), *marks(after)]

    if found < len(path):
        return "\n".join(_insert(lines, spans, found, path, rendered(0))) + "\n"
    head, stop, indent = spans[-1]
    value = _value_text(lines[head], path[-1], indent)
    if value == "[]":
        lines[head] = re.sub(r"\[\][ ]*", "", lines[head], count=1).rstrip(" ")
        return "\n".join([*lines[: head + 1], *rendered(indent + 2), *lines[head + 1 :]]) + "\n"
    if value:
        raise ValueError(f"`{'.'.join(path)}` is written on one line; write it as a block, one `- ` item per entry, to add to it")
    child = next((_indent_of(lines[i]) for i in range(head + 1, stop) if _is_item(lines[i].strip())), indent + 2)
    return "\n".join([*lines[:stop], *rendered(child), *lines[stop:]]) + "\n"


def append_item(text: str, path: str | tuple[str, ...], item: Any) -> str:
    """`text` with `item` added as the last entry of the block sequence at `path`; see append_items."""
    return append_items(text, path, [item])


def set_entry(text: str, path: str | tuple[str, ...], field: str, value: Any) -> str:
    """`text` with `field: value` set in the block mapping at `path` (a key, or keys from the top), which is created when
    missing. An existing `field` is replaced in place, with what it held; a mapping in flow style is a ValueError."""
    path = (path,) if isinstance(path, str) else path
    lines = _split(text)
    entry = f"{key(field)}: {flow(value)}"
    spans, found = _locate(lines, path)
    if found < len(path):
        return "\n".join(_insert(lines, spans, found, path, [entry])) + "\n"
    head, stop, indent = spans[-1]
    if _value_text(lines[head], path[-1], indent):
        raise ValueError(f"`{'.'.join(path)}` is written on one line; write it as a block, one `field: value` per line, to set a field")
    child = _child(lines, spans[-1])
    span = _span(lines, field, head + 1, stop, child)
    if span:
        lines[span[0] : span[1]] = [" " * child + entry]
        return "\n".join(lines) + "\n"
    return "\n".join([*lines[:stop], " " * child + entry, *lines[stop:]]) + "\n"
