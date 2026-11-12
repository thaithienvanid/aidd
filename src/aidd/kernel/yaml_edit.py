"""Edits to YAML text that change one key and nothing else: a person's comments, key order, quoting, blank lines, and
indentation stay. Each edit finds a key by its path (`strict_yaml.key_lines` gives the line it starts on) and returns the new
text, or None when it cannot place the key on a line of its own, such as a key inside a flow mapping `{a: 1}`. The caller
reads the result again (`strict_yaml.load`) and compares it with the data it expects, so an edit that went wrong is refused.
Text uses `\\n`; a caller that holds another line ending converts it."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from aidd.kernel import strict_yaml

Step = str | int
# The start of a line that holds a key: its indentation and any `- ` item marks, then the key (plain or double-quoted), then the colon.
_KEY_LINE = re.compile(r'(?P<lead>[ ]*(?:-[ ]+)*)(?P<key>"(?:[^"\\]|\\.)*"|[A-Za-z_][A-Za-z0-9_.-]*):(?=[ ]|$)')


@dataclass(frozen=True)
class Spot:
    """Where a key is: its lines are `first` up to `end` (the key and everything under it), the key starts at column `col`,
    and `dash` says that an item mark `- ` comes before it on its line."""

    first: int
    end: int
    col: int
    dash: bool
    token_end: int


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def locate(text: str, path: tuple[Step, ...]) -> Spot | None:
    """The place of the key at `path` (keys, and list positions as integers), or None when no line of its own holds it."""
    mark = "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in path)
    number = strict_yaml.key_lines(text).get(mark)
    if number is None or not isinstance(path[-1], str):
        return None
    lines = text.split("\n")
    found = _KEY_LINE.match(lines[number - 1])
    if found is None:
        return None
    token = found.group("key")
    if (json.loads(token) if token.startswith('"') else token) != path[-1]:
        return None
    col = len(found.group("lead"))
    rest = lines[number - 1][found.end() :]
    keeps_items = not rest.split("#", 1)[0].strip() and "-" not in found.group("lead")
    end = number
    while end < len(lines):
        line = lines[end]
        if not line.strip():
            end += 1
        elif _indent(line) > col or (keeps_items and _indent(line) == col and line.lstrip().startswith("- ")):
            end += 1
        else:
            break
    while end > number and not lines[end - 1].strip():
        end -= 1
    return Spot(number - 1, end, col, "-" in found.group("lead"), col + len(token))


def rename_key(text: str, path: tuple[Step, ...], new: str) -> str | None:
    """`text` with the key at `path` written as `new`; its value, its comment, and its place stay."""
    spot = locate(text, path)
    if spot is None:
        return None
    lines = text.split("\n")
    line = lines[spot.first]
    lines[spot.first] = line[: spot.col] + strict_yaml.key(new) + line[spot.token_end :]
    return "\n".join(lines)


_VALUE = re.compile(r"""(?P<space>[ ]*)(?P<value>"(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|[^#\s][^#]*?)(?P<tail>[ ]+\#.*|[ ]*)""")


def set_value(text: str, path: tuple[Step, ...], value: object) -> str | None:
    """`text` with the value of the key at `path` written as `value` (a scalar, `[a, b]`, or `{k: v}`), on the key's own line, its
    comment kept. None when the key has no one-line scalar value there, such as a block or a flow collection."""
    spot = locate(text, path)
    if spot is None or spot.end != spot.first + 1:
        return None
    lines = text.split("\n")
    rest = lines[spot.first][spot.token_end + 1 :]
    found = _VALUE.fullmatch(rest)
    if found is None or found.group("value")[0] in "[{|>&*!":
        return None
    lines[spot.first] = f"{lines[spot.first][: spot.token_end + 1]} {strict_yaml.flow(value)}{found.group('tail')}"
    return "\n".join(lines)


def cut(text: str, path: tuple[Step, ...], *, parent_empty: bool = False) -> str | None:
    """`text` without the key at `path` and the lines under it (a block mapping, a list, or a literal block). A comment above
    it stays. When the key was the only one in its mapping, `parent_empty` says so, and the mapping's key reads `{}`. None for
    a key that is the only one of its list item: that item would hold nothing."""
    spot = locate(text, path)
    if spot is None:
        return None
    lines = text.split("\n")
    parent = locate(text, path[:-1]) if parent_empty and len(path) > 1 and isinstance(path[-2], str) else None
    if spot.dash:
        sibling = lines[spot.end] if spot.end < len(lines) else ""
        if not sibling.strip() or _indent(sibling) != spot.col or sibling.lstrip().startswith(("- ", "#")):
            return None
        lines[spot.first] = lines[spot.first][: spot.col] + sibling[spot.col :]
        del lines[spot.first + 1 : spot.end + 1]
        return "\n".join(lines)
    if parent_empty:
        if parent is None:
            return None
        head = re.fullmatch(r"(.*?:)([ ]*)(#.*)?", lines[parent.first])
        if head is None:
            return None
        lines[parent.first] = f"{head.group(1)} {{}}" + (f"  {head.group(3)}" if head.group(3) else "")
    del lines[spot.first : spot.end]
    return "\n".join(lines)


def append_key(text: str, key: str, value: object) -> str:
    """`text` with `key: value` as a last top-level line."""
    body = text.rstrip("\n")
    return (body + "\n" if body else "") + f"{strict_yaml.key(key)}: {strict_yaml.flow(value)}" + ("\n" if text.endswith("\n") or not body else "")
