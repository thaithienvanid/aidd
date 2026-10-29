"""Text aidd writes: a Markdown table cell, a value or `n/a`, a template filled from its `{{token}}` values,
a slug, and a code's anchor on docs/ERRORS.md."""

from __future__ import annotations

import json
import re

from aidd.kernel import strict_yaml


def md_cell(text: object, newline: str = " ") -> str:
    """Text safe inside one Markdown table cell: pipes escaped, newlines replaced with `newline`."""
    return str(text or "").replace("|", "\\|").replace("\n", newline)


def na(value: object) -> str:
    """A value as a report shows it: `n/a` when there is none."""
    return "n/a" if value is None else str(value)


_FRONT = re.compile(r"\A---\n.*?\n---\n", re.S)


_TOKEN = re.compile(r"\{\{(\w+)\}\}")
# In front matter: a token that is a whole double-quoted value, with the spaces before a trailing comment; or any token.
_FRONT_TOKEN = re.compile(r'"\{\{(\w+)\}\}"(?:( +)#)?|\{\{(\w+)\}\}')


def fill_template(text: str, **values: str) -> str:
    """Replace every {{token}}; a token without a value means the template and the code drifted apart. Values are raw
    text, filled in one pass: a value that holds `{{x}}` stays as written, never read as a template again. In YAML
    front matter a token that is a whole double-quoted value (`title: "{{title}}"`) becomes that value as a YAML scalar,
    plain where that is safe (a trailing comment keeps its column), and a token inside a quoted string is escaped for
    it; the body gets the raw value."""
    left = sorted(set(_TOKEN.findall(text)) - set(values))
    if left:
        raise ValueError(f"template tokens without a value: {', '.join(left)}")
    m = _FRONT.match(text)
    front, body = (text[: m.end()], text[m.end() :]) if m else ("", text)

    def in_front(t: re.Match[str]) -> str:
        if t.group(1) is None:
            return json.dumps(values[t.group(3)], ensure_ascii=False)[1:-1]
        value = strict_yaml.scalar(values[t.group(1)])
        return value + " " * max(1, len(t.group(0)) - len(value) - 1) + "#" if t.group(2) else value

    return _FRONT_TOKEN.sub(in_front, front) + _TOKEN.sub(lambda t: values[t.group(1)], body)


def slug(text: str) -> str:
    """A file-name form of a topic: lowercase words joined by hyphens."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60].strip("-") or "doc"


def code_anchor(code: str) -> str:
    """A code's anchor on docs/ERRORS.md: lowercase, each run of other characters one hyphen (`scope.outside` is
    `scope-outside`, `change_request.several_specs` is `change-request-several-specs`). The page prefixes a step code's anchor with
    `step-`, a guard reason's with `guard-`, and an exit code's with `exit-`; a finding code's has no prefix."""
    return re.sub(r"[^a-z0-9]+", "-", code.lower()).strip("-")


def series(items: list[str], conj: str) -> str:
    """`a, b, and c` (or `a and b`): items as one phrase; an empty list is an empty phrase."""
    if not items:
        return ""
    if len(items) == 2:
        return f"{items[0]} {conj} {items[1]}"
    return ", ".join(items[:-1]) + f", {conj} {items[-1]}" if len(items) > 1 else items[0]
