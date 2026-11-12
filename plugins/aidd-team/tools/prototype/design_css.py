"""The prototype tool's CSS reader and its depth rule: what a declaration is in a design, and which depth it may draw.

This file sits beside `design_checks.py` and belongs to the same tool. It uses the standard library only. It owns two things:

- the declaration reader, which gives the raw-color rule and the depth rule the same whole declarations: a comment, read
  only where a browser reads one, is no declaration, a value that continues on the next line is one value, and nothing in the `<style id="tokens">` block is read,
  because the tokens block is where a design may hold any value, and an at-rule's condition is no declaration, so
  `@supports (backdrop-filter: blur(10px))` tests a feature and draws nothing;
- the depth rule: outside the tokens block, a `box-shadow` or `text-shadow` layer is a ring or wholly `var(...)`, and a
  `blur(` or `drop-shadow(` in `filter` or `backdrop-filter` is zero or wholly `var(...)`. A ring is a shadow layer whose
  offsets and blur are all zero, so it draws an edge and no depth.

The reader is linear in the size of the text, so a hostile design takes time in proportion to its length. Text from the
design is data: nothing here runs it. SVG filters, paint servers, and a gradient are no part of the depth rule: a gradient
made of tokens is made of tokens already, and the raw-color rule owns one that is not.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import NamedTuple

# Where CSS stands in a page: a `<style>` element's text, and a `style` attribute's value. A `/* */` is a comment only there,
# and a `<!-- -->` only outside them, as a browser reads them.
_HTML_TOKEN = re.compile(r"""<!--|<style(?=[\s/>])[^<>]*>|(?<![\w-])style\s*=\s*(?=["'])""", re.I)
# The end tag as a browser reads it. A search for it stops before the text's last `>`: a candidate then always has a `>` to end at,
# so the first one ends the search, and a text with many `</style ` and no `>` costs one pass, not one for each.
_STYLE_END = re.compile(r"</style(?:[\s/][^>]*)?>", re.I)
_TOKENS_OPEN = '<style id="tokens">'
# Inside CSS, a string and an unquoted `url(` hold text, so a `/*` in one opens no comment. A string ends at its quote or its line.
_CSS_TOKEN = re.compile(r"""\"(?:\\.|[^"\\\n])*"?|'(?:\\.|[^'\\\n])*'?|url\(\s*(?!["'\s])[^)\s]*|/\*""", re.I)
_CUSTOM_PROPERTY = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;}]+)")
# A declaration ends at `;`, `}`, `{`, or `"` (the end of a style attribute), and at `<`, which no CSS value holds: a tag
# ends the text a declaration could run on into.
_SEGMENT = re.compile(r'[^;"}{<]+')
# An at-rule's prelude: the segment starts with `@`, after the rest of a tag that ends the text before it, such as `style>`.
_AT_RULE = re.compile(r"(?:[^@:]*>)?\s*@")
_DEPTH_PROPERTY = re.compile(r"(?<![\w.#-])(?:-webkit-)?(box-shadow|text-shadow|filter|backdrop-filter)\s*:", re.I)
_IMPORTANT = re.compile(r"!\s*important\s*$", re.I)
# A CSS length: a number, with a unit or none. A zero is any spelling of 0 in any unit.
_LENGTH = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?(?:[a-z]+|%)?", re.I)
_ZERO = re.compile(r"[+-]?(?:0+\.?0*|\.0+)(?:[a-z]+|%)?", re.I)
_FILTER_FUNCTION = re.compile(r"(blur|drop-shadow)\((.*)\)", re.I | re.S)
# The values every property takes, which draw nothing of their own.
_NO_DEPTH = frozenset("none inherit initial unset revert revert-layer".split())
_MIN_LENGTHS, _MAX_LENGTHS = 2, 4  # x and y, up to blur and spread
_FALLBACK_LEVELS = 8  # how deep a `var()` may hold another in its fallback
_ZERO_LENGTHS = 3  # x, y, and blur are zero in a ring; a fourth length is the spread, which may be any length


class Declaration(NamedTuple):
    """One declaration's text, with the line where its text starts. A property may sit on a later line of its text."""

    line: int
    text: str

    def line_at(self, index: int) -> int:
        """The line of the character at `index` of the text."""
        return self.line + self.text.count("\n", 0, index)


class DepthFinding(NamedTuple):
    start: int  # where the property starts in the declaration's text
    prop: str  # the property, lowercase and without a vendor prefix
    layer: str  # the shadow layer or the filter function that draws depth
    value: str  # the whole value of the property


def normal(value: str) -> str:
    """A value as the tokens block is searched for it: lowercase, with each run of space one space."""
    return " ".join(value.lower().split())


def _css_comments(text: str, begin: int, stop: int) -> Iterator[tuple[int, int]]:
    """The comments of the CSS in `text[begin:stop]`, each as its start and end. A comment that is never closed is no comment:
    it is text, as are the `/*` after it, because the rest of the CSS holds no end for them."""
    pos = begin
    while (found := _CSS_TOKEN.search(text, pos, stop)) is not None:
        pos = found.end()
        if found.group(0) != "/*":
            continue
        end = text.find("*/", pos, stop)
        if end < 0:
            return
        yield found.start(), end + 2
        pos = end + 2


def _comments(text: str) -> Iterator[tuple[int, int]]:
    """The comments of the page, in order: each `/* */` in a `<style>` element or a `style` value, and each `<!-- -->` outside both."""
    pos, html_closes, room = 0, True, text.rfind(">") + 1  # html_closes: false once the rest of the text holds no `-->`
    while (found := _HTML_TOKEN.search(text, pos)) is not None:
        token = found.group(0)
        pos = found.end()
        if token == "<!--":
            end = text.find("-->", pos) if html_closes else -1
            html_closes = end >= 0
            if end >= 0:
                yield found.start(), end + 3
                pos = end + 3
        elif token[0] == "<":
            stop = _STYLE_END.search(text, pos, room)
            end = stop.start() if stop else len(text)
            yield from _css_comments(text, pos, end)
            pos = stop.end() if stop else end
        else:
            end = text.find(text[pos], pos + 1)
            if end >= 0:
                yield from _css_comments(text, pos + 1, end)
                pos = end


def _masked(text: str) -> str:
    """The text with each comment replaced by one space and its newlines, so a line keeps its number."""
    parts: list[str] = []
    pos = 0
    for start, end in _comments(text):
        parts += [text[pos:start], " " + "\n" * text.count("\n", start, end)]
        pos = end
    return "".join(parts) + text[pos:]


def _token_spans(text: str) -> Iterator[tuple[int, int]]:
    """Where each `<style id="tokens">` block stands: from its opening tag to the end of its end tag, or to the end of the text."""
    pos, room = 0, text.rfind(">") + 1
    while (start := text.find(_TOKENS_OPEN, pos)) >= 0:
        stop = _STYLE_END.search(text, start + len(_TOKENS_OPEN), room)
        pos = stop.end() if stop else len(text)
        yield start, pos


def token_blocks(text: str) -> list[str]:
    """The body of each `<style id="tokens">` block."""
    return [text[start + len(_TOKENS_OPEN) : end] for start, end in _token_spans(text)]


def custom_properties(block: str) -> list[tuple[str, str]]:
    """The custom properties a block of CSS sets, each as (name, value)."""
    return [(found.group(1), found.group(2).strip()) for found in _CUSTOM_PROPERTY.finditer(block)]


def declarations(text: str) -> list[Declaration]:
    """The declarations of the file outside the tokens block, in the order they stand, as a browser would read them."""
    text = _masked(text)
    spans = iter([*_token_spans(text), (len(text) + 1, len(text) + 1)])
    span = next(spans)
    found_all: list[Declaration] = []
    line, seen = 1, 0
    for found in _SEGMENT.finditer(text):
        while span[1] <= found.start():
            span = next(spans)
        if span[0] <= found.start() or _AT_RULE.match(found.group(0)):
            continue  # inside the tokens block, or an at-rule's condition, which tests a feature and sets nothing
        line += text.count("\n", seen, found.start())
        seen = found.start()
        found_all.append(Declaration(line, found.group(0)))
    return found_all


def _split_top(text: str, comma: bool) -> list[str]:
    """`text` cut at each comma, or at each run of space, that is not inside parentheses."""
    parts: list[str] = []
    depth, start = 0, 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and (char == "," if comma else char.isspace()):
            parts.append(text[start:index])
            start = index + 1
    parts.append(text[start:])
    return [part.strip() for part in parts if part.strip()]


def is_var(text: str) -> bool:
    """Whether the text is one `var(...)`, whole."""
    if not text.startswith("var("):
        return False
    depth = 0
    for index in range(3, len(text)):
        depth += (text[index] == "(") - (text[index] == ")")
        if depth == 0:
            return index == len(text) - 1
    return False


def _is_length(token: str) -> bool:
    return _LENGTH.fullmatch(token) is not None or token.lower().startswith("calc(")


def is_ring(layer: str) -> bool:
    """Whether a shadow layer is a ring: two to four lengths (x, y, blur, spread), a color before or after them, and
    `inset`. It is a ring when x, y, and blur are zero, in any unit, with any spread: it draws an edge and no depth."""
    words = _split_top(layer, comma=False)
    tokens = [word for word in words if word.lower() != "inset"]
    if not tokens or len(words) - len(tokens) > 1:
        return False  # nothing but `inset`, or `inset` twice
    if not _is_length(tokens[0]):
        tokens = tokens[1:]  # the color comes first
    elif not _is_length(tokens[-1]):
        tokens = tokens[:-1]  # the color comes last
    if not _MIN_LENGTHS <= len(tokens) <= _MAX_LENGTHS:
        return False
    return all(_ZERO.fullmatch(token) if index < _ZERO_LENGTHS else _is_length(token) or is_var(token) for index, token in enumerate(tokens))


def shadow_layers(value: str) -> list[str]:
    """The layers of a `box-shadow` or `text-shadow` value, each judged by itself. `none` and the values every property takes
    are no layer."""
    return [] if normal(value) in _NO_DEPTH else _split_top(value, comma=True)


def _clean(value: str) -> str:
    """A value as the rule reads it: no `!important`, and no text after a quote that ends a style attribute in single quotes."""
    depth = 0
    for index, char in enumerate(value):
        depth += (char == "(") - (char == ")")
        if char == "'" and depth <= 0:
            value = value[:index]
            break
    return _IMPORTANT.sub("", value.strip()).strip()


def _shadow_layer(value: str) -> str:
    """The first layer of a shadow value that draws depth, or an empty string. A layer is a ring, or a `var(...)` whose fallback,
    read as a value, draws none. A fallback nested deeper than a design needs is read as depth, so a hostile one costs no more
    than its length times that depth."""
    todo = [(value, 0)]
    while todo:
        text, level = todo.pop()
        for one in shadow_layers(text):
            if not is_var(one):
                if not is_ring(one):
                    return one
            elif level == _FALLBACK_LEVELS:
                return one
            elif fallback := one[4:-1].partition(",")[2].strip():
                todo.append((fallback, level + 1))
    return ""


def _filter_layer(value: str) -> str:
    """The first `blur(` or `drop-shadow(` of a filter value that is not zero and not `var(...)`, or an empty string."""
    for token in [] if normal(value) in _NO_DEPTH else _split_top(value, comma=False):
        function = _FILTER_FUNCTION.fullmatch(token)
        if function is None:
            continue
        name, argument = function.group(1).lower(), function.group(2).strip()
        calm = is_var(argument) or (_ZERO.fullmatch(argument) if name == "blur" else is_ring(argument))
        if not calm:
            return token
    return ""


def depth_finding(text: str) -> DepthFinding | None:
    """The depth a declaration's text draws, when it draws any outside the rule: the property is `box-shadow`,
    `text-shadow`, `filter`, or `backdrop-filter`, and a layer or a function in its value is neither a ring, zero, nor
    wholly `var(...)`. The declaration holds one property, so the first is the one read."""
    found = _DEPTH_PROPERTY.search(text)
    if found is None:
        return None
    prop, value = found.group(1).lower(), _clean(text[found.end() :])
    if not value:
        return None
    layer = _shadow_layer(value) if prop.endswith("shadow") else _filter_layer(value)
    return DepthFinding(found.start(), prop, layer, value) if layer else None
