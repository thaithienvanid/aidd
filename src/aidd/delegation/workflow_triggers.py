"""What a GitHub workflow's `on:` says about a push, read fully and exactly, or not at all. The delegate check, `aidd doctor`,
and `aidd init` all ask this module, so the three agree.

The reader takes the one top-level `on:` key and reads its value in a small subset of YAML: block mappings and sequences,
flow lists and maps (over several lines too), and plain or quoted scalars, with comments dropped. Any other shape is
unread: an alias, a tag, a block scalar, a tab, a control character, a quote that does not close, a list that does not
close, a duplicate key, or an `on:` it cannot find once. A workflow whose trigger is unread counts as running on every
branch and tag, so nothing in how the file is written can make the scan say "does not deploy" when GitHub would run it."""

from __future__ import annotations

import dataclasses
import re
from typing import Any

from aidd.kernel import globs

# The triggers that never run a workflow because a branch moved: a review, an issue, a manual run, a release. Any other
# counts as reaching it: `workflow_run` after a test workflow, `schedule` on the default branch, a name this does not know,
# and `pull_request`, `pull_request_target`, and `merge_group`, because a deploy on a merge (`types: [closed]`), on a push to a
# pull request's branch, or from the merge queue is a deploy a branch moved started.
NOT_ON_MERGE = frozenset(
    {
        "pull_request_review",
        "pull_request_review_comment",
        "issues",
        "issue_comment",
        "workflow_dispatch",
        "release",
        "discussion",
        "discussion_comment",
        "label",
        "milestone",
        "watch",
        "fork",
    }
)
GITHUB_PATTERN_CHARS = "?+[]\\"
PUSH_KEYS = frozenset({"branches", "tags", "paths", "paths-ignore"})
MAX_DEPTH = 16
# The key a YAML 1.1 reader takes as `on`, in any case and quoting: more than one of them is unread.
_ON_KEY = re.compile(r"""^(?:on|true|yes|y|"on"|"true"|"yes"|"y"|'on'|'true'|'yes'|'y')\s*:(.*)$""", re.I)
_PLAIN_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*\s*:(?:\s|$)")
# Characters that end a line for `splitlines` and not for a YAML reader (or the reverse): a file that holds one is unread.
_BREAKS = re.compile(r"[\x0b\x0c\x1c-\x1e\x85\u2028\u2029]")
_MARKER = re.compile(r"(?:---|\.\.\.)(?:\s|$)")
_KEY = re.compile(r"""^("[^"\\]*"|'(?:[^']|'')*'|[A-Za-z0-9_.-]+)\s*:(?:\s+(.*))?$""")
_DOUBLE = re.compile(r'"[^"\\]*"')
_SINGLE = re.compile(r"'(?:[^']|'')*'")
_UNSAFE = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029\ufeff\ufffe\uffff\ud800-\udfff]")
# What a plain scalar cannot start with: an anchor, an alias, a tag, a block scalar, a directive, or a reserved indicator.
_NOT_PLAIN_START = "&*!|>%@`?#,]}"


class Unread(ValueError):
    """A shape this reader does not read."""


@dataclasses.dataclass(frozen=True)
class Push:
    """A workflow's `push` trigger. `branches` and `tags` are the lists it names (None: it names none), and `wide` is true when
    it runs on more than a list names or has a filter this could not read: `branches-ignore`, `tags-ignore`, a shape that is
    not a list of names, or a pattern with a character GitHub reads as more than a glob (`?`, `+`, `[`, `]`, `\\`)."""

    branches: tuple[str, ...] | None = None
    tags: tuple[str, ...] | None = None
    wide: bool = False


@dataclasses.dataclass(frozen=True)
class Triggers:
    """What `on:` says: its `push` trigger (None: it has none), and whether another trigger, such as `workflow_run`, may run
    the workflow after a merge."""

    push: Push | None = None
    other: bool = False


def strip_comment(text: str) -> str:
    """`text` without a trailing ` # comment`. A `#` inside quotes stays; a quote that never closes ends the scan, and the
    readers that follow refuse the line."""
    quote = ""
    for i, ch in enumerate(text):
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or text[i - 1] in " \t"):
            return text[:i].rstrip()
    return text


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_item(text: str) -> bool:
    return text == "-" or text.startswith("- ")


def _region(text: str) -> tuple[str, list[tuple[int, str]]]:
    """The one top-level `on:` line's value on that line, and the lines under it as (indent, text): no blank line, no comment line
    at any indent, and no trailing comment. They end at the next line at the left margin that is not a `- ` item or the close of a flow collection."""
    if _BREAKS.search(text):
        raise Unread("a character that some readers take as a line break")
    raw = text.splitlines()
    live = [i for i, line in enumerate(raw) if line.strip() and not line.lstrip().startswith("#")]
    keys = [(i, m) for i in live if (m := _ON_KEY.match(raw[i]))]
    if any(_MARKER.match(raw[i]) for i in live[1:]) or len(keys) != 1:
        raise Unread("no single `on:` key, or more than one document")
    at, key = keys[0]
    _check_document(raw, live, at)
    first = strip_comment(key.group(1)).strip()
    lines: list[tuple[int, str]] = []
    for i in live:
        if i <= at:
            continue
        line = raw[i]
        if _indent(line) == 0 and not (_is_item(line) or line[0] in "]}"):
            break
        content = strip_comment(line.lstrip(" ")).strip()
        if "\t" in line[: _indent(line) + 1] or _UNSAFE.search(content):
            raise Unread("a tab or a control character")
        lines.append((_indent(line), content))
    if _UNSAFE.search(first):
        raise Unread("a control character")
    return first, lines


def _check_document(raw: list[str], live: list[int], at: int) -> None:
    """Refuse a document whose `on:` key at line `at` may not be the key a reader finds there. The document must be a block mapping
    from its first line, every column-0 line a plain key (so no flow map, `?` key, anchor, tag, merge key, or quoted key can
    stand for `on`), and no quote or flow collection still open when `on:` is reached. Lines under `on:` are read by the caller."""
    body = live[1:] if strip_comment(raw[live[0]]).strip() == "---" else live
    if not body or _indent(raw[body[0]]) != 0:
        raise Unread("the document is not a block mapping from its first line")
    flow, in_region = "", True
    for i in body:
        line, content = raw[i], strip_comment(raw[i].strip()).strip()
        if i < at:
            if _indent(line) and flow and _balance(flow) > 0:
                flow += " " + content
            elif _indent(line) == 0:
                if flow and _balance(flow) > 0 or not _PLAIN_KEY.match(line):
                    raise Unread("a line before `on:` that a reader could take for part of a value")
                value = strip_comment(line.split(":", 1)[1]).strip()
                flow = value if value[:1] in ("[", "{", '"', "'") else ""
        elif i == at:
            if flow and _balance(flow) > 0:
                raise Unread("a flow collection still open at `on:`")
        elif _indent(line) == 0:
            in_region = in_region and (_is_item(line) or line[0] in "]}")
            if not in_region and not _PLAIN_KEY.match(line):
                raise Unread("a line after `on:` that is not a plain key")
    if flow:
        _balance(flow)


def _balance(text: str) -> int:
    """How many `[` and `{` of a flow collection are still open in `text`. A quote that never closes is unread."""
    depth, quote = 0, ""
    for ch in text:
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
    if quote:
        raise Unread("a quote that does not close")
    return depth


def _scalar(text: str) -> str | None:
    """A whole quoted or plain scalar. A quoted one holds no escape, and a plain one no `: `, no quote, and no indicator at its
    start, so a value that could mean more than its text says is unread."""
    if _DOUBLE.fullmatch(text):
        return text[1:-1]
    if _SINGLE.fullmatch(text):
        return text[1:-1].replace("''", "'")
    if not text or text[0] in _NOT_PLAIN_START or text.startswith("- ") or re.search(r"""[\"']|:(\s|$)""", text) or text[0] in "[{":
        raise Unread("a scalar this does not read")
    return None if text in ("~", "null", "Null", "NULL") else text


def _skip(text: str, pos: int) -> int:
    while pos < len(text) and text[pos] == " ":
        pos += 1
    return pos


def _flow_scalar(text: str, pos: int) -> tuple[str | None, int]:
    """The scalar of a flow collection at `pos`, quoted or plain, and where it ends."""
    for quoted in (_DOUBLE, _SINGLE):
        found = quoted.match(text, pos)
        if found:
            return _scalar(found.group(0)), found.end()
    end = pos
    while end < len(text) and text[end] not in ",[]{}" and not (text[end] == ":" and (end + 1 == len(text) or text[end + 1] in " ,[]{}")):
        end += 1
    return _scalar(text[pos:end].strip()), end


def _flow_value(text: str, pos: int, depth: int) -> tuple[Any, int]:
    """A flow list, a flow map, or a scalar at `pos`, and where it ends."""
    if depth > MAX_DEPTH:
        raise Unread("a flow collection nested too deep")
    pos = _skip(text, pos)
    if pos >= len(text):
        raise Unread("a value is missing")
    if text[pos] not in "[{":
        return _flow_scalar(text, pos)
    close, pos = "]" if text[pos] == "[" else "}", pos + 1
    items: list[Any] = []
    mapping: dict[str, Any] = {}
    while True:
        pos = _skip(text, pos)
        if pos >= len(text):
            raise Unread("a flow collection that does not close")
        if text[pos] == close:
            return (mapping if close == "}" else items), pos + 1
        if close == "]":
            value, pos = _flow_value(text, pos, depth + 1)
            items.append(value)
        else:
            key, pos = _flow_scalar(text, pos)
            if key is None or key in mapping:
                raise Unread("a key this does not read, or twice")
            pos = _skip(text, pos)
            value = None
            if pos < len(text) and text[pos] == ":":
                pos = _skip(text, pos + 1)
                if pos < len(text) and text[pos] not in ",}":
                    value, pos = _flow_value(text, pos, depth + 1)
            mapping[key] = value
        pos = _skip(text, pos)
        if pos < len(text) and text[pos] == ",":
            pos += 1
        elif pos >= len(text) or text[pos] != close:
            raise Unread("a flow collection this does not read")


class _Reader:
    """A block of (indent, text) lines read in order."""

    def __init__(self, lines: list[tuple[int, str]]) -> None:
        self.lines, self.i = lines, 0
        self.top = lines[0][0] if lines else 0  # the indent of the trigger names, whose values only `push` needs read

    def peek(self) -> tuple[int, str] | None:
        return self.lines[self.i] if self.i < len(self.lines) else None

    def flow(self, first: str) -> Any:
        """A flow collection starting with `first`, over as many following lines as it needs to close."""
        text = first
        while _balance(text) > 0:
            more = self.peek()
            if more is None:
                raise Unread("a flow collection that does not close")
            self.i += 1
            text += " " + more[1]
        value, end = _flow_value(text, 0, 0)
        if text[end:].strip():
            raise Unread("text after a flow collection")
        return value

    def inline(self, rest: str) -> Any:
        return self.flow(rest) if rest[0] in "[{" else _scalar(rest)

    def under(self, indent: int) -> Any:
        """The value on the lines under a key at `indent`: a block, a flow collection on its own line, a list at the key's own
        indent, or null when nothing is under it."""
        nxt = self.peek()
        if nxt is not None and nxt[0] > indent:
            if nxt[1][0] in "[{":
                self.i += 1
                return self.flow(nxt[1])
            return self.block(nxt[0])
        if nxt is not None and nxt[0] == indent and _is_item(nxt[1]):
            return self.sequence(indent)
        return None

    def block(self, indent: int) -> Any:
        line = self.peek()
        assert line is not None
        return self.sequence(indent) if _is_item(line[1]) else self.mapping(indent)

    def sequence(self, indent: int) -> list:
        items = []
        while (line := self.peek()) is not None and line[0] == indent and _is_item(line[1]):
            rest = line[1][1:].strip()
            if not rest:
                raise Unread("a list item with no value on its line")
            self.i += 1
            value = self.inline(rest)
            if value is None or isinstance(value, dict):
                raise Unread("a list item that is not a name")
            items.append(value)
        return items

    def mapping(self, indent: int) -> dict[str, Any]:
        out: dict[str, Any] = {}
        while (line := self.peek()) is not None and line[0] >= indent:
            key = _KEY.match(line[1])
            if line[0] != indent or _is_item(line[1]) or not key or key.group(1).strip("\"'") in out:
                raise Unread("a line this does not read as a key")
            name = str(_scalar(key.group(1)) if key.group(1)[0] in "\"'" else key.group(1))
            self.i += 1
            rest = (key.group(2) or "").strip()
            if indent == self.top and name != "push":
                self.skip(indent)  # another trigger counts by its name alone
                out[name] = None
            else:
                out[name] = self.inline(rest) if rest else self.under(indent)
        return out

    def skip(self, indent: int) -> None:
        """Pass the lines under a key at `indent`."""
        while (line := self.peek()) is not None and (line[0] > indent or (line[0] == indent and _is_item(line[1]))):
            self.i += 1


def _on_value(text: str) -> Any:
    first, lines = _region(text)
    reader = _Reader(lines)
    value = reader.inline(first) if first else reader.under(0)
    if reader.peek() is not None:
        raise Unread("lines left over under `on:`")
    return value


def _names(value: Any) -> tuple[str, ...] | None:
    """A list of names from a string or a non-empty list of strings; None for anything else, which is unread."""
    names = (value,) if isinstance(value, str) else tuple(value) if isinstance(value, list) else ()
    return names if names and all(isinstance(n, str) and n for n in names) else None


def _push(value: Any) -> Push:
    if value is None:
        return Push()
    if not isinstance(value, dict):
        return Push(wide=True)
    lists = {k: _names(value[k]) if k in value else None for k in ("branches", "tags")}
    unread = any(k in value and lists[k] is None for k in lists)
    # In GitHub's filter `?`, `+`, `[...]`, and `\` mean more than aidd's glob says, so a pattern with one matches more than it reads as.
    unread = unread or any(c in n for names in lists.values() for n in names or () for c in GITHUB_PATTERN_CHARS)
    return Push(lists["branches"], lists["tags"], wide=unread or any(k not in PUSH_KEYS for k in value))


def read_triggers(text: str) -> Triggers | None:
    """What a workflow's `on:` says, or None when it is unread."""
    try:
        value = _on_value(text)
    except (Unread, RecursionError):
        return None
    if isinstance(value, str):
        value = [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        value = dict.fromkeys(value)
    if not isinstance(value, dict) or not value:
        return None
    return Triggers(_push(value["push"]) if "push" in value else None, any(k not in NOT_ON_MERGE and k != "push" for k in value))


def push_reaches(text: str, branch: str) -> bool:
    """Whether a workflow's `on:` runs it on a push to `branch`. A trigger or a filter it cannot read, a `branches-ignore`, a
    negated glob, and a trigger such as `workflow_run` all count as reaching, so production fails closed."""
    triggers = read_triggers(text)
    if triggers is None or triggers.other:
        return True
    push = triggers.push
    if push is None:
        return False
    if push.wide:
        return True
    if push.branches is not None:
        return any(n.startswith("!") or globs.match(n, branch) for n in push.branches)
    return push.tags is None  # a push filtered to tags alone reaches no branch; a paths filter still may
