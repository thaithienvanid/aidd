"""Text aidd writes: a Markdown table cell, a value or `n/a`, a template filled from its `{{token}}` values,
and a slug."""

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


def _fill_quoted(front: str, token: str, value: str) -> str:
    """Each `"{{token}}"` in YAML front matter as `value`, a YAML scalar; a trailing comment keeps its column."""

    def put(m: re.Match[str]) -> str:
        return value + " " * max(1, len(m.group(0)) - len(value) - 1) + "#" if m.group(1) else value

    return re.sub(re.escape(f'"{token}"') + r"(?:( +)#)?", put, front)


def fill_template(text: str, **values: str) -> str:
    """Replace every {{token}}; a token left over means the template and the code drifted apart. Values are raw text.
    In YAML front matter a token that is a whole double-quoted value (`title: "{{title}}"`) becomes that value as a YAML
    scalar, plain where that is safe, and a token inside a quoted string is escaped for it; the body gets the raw value."""
    m = _FRONT.match(text)
    front, body = (text[: m.end()], text[m.end() :]) if m else ("", text)
    for k, v in values.items():
        token = "{{" + k + "}}"
        if front:
            front = _fill_quoted(front, token, strict_yaml.scalar(v)).replace(token, json.dumps(v, ensure_ascii=False)[1:-1])
        body = body.replace(token, v)
    text = front + body
    left = sorted(set(re.findall(r"\{\{(\w+)\}\}", text)))
    if left:
        raise ValueError(f"template tokens without a value: {', '.join(left)}")
    return text


def slug(text: str) -> str:
    """A file-name form of a topic: lowercase words joined by hyphens."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60].strip("-") or "doc"


def series(items: list[str], conj: str) -> str:
    """`a, b, and c` (or `a and b`): items as one phrase."""
    if len(items) == 2:
        return f"{items[0]} {conj} {items[1]}"
    return ", ".join(items[:-1]) + f", {conj} {items[-1]}" if len(items) > 1 else items[0]
