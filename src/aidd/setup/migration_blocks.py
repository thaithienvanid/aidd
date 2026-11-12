"""One piece of a file that `aidd upgrade` edits (setup.migrating): its text, the data it should hold once the edits made to its text
are done, and the edits, one key at a time (kernel.yaml_edit). A JSON file reads as JSON; any other reads as aidd's YAML."""

from __future__ import annotations

import json
from typing import Any

from aidd.kernel import documents, retired_names, strict_yaml, yaml_edit

Key = tuple[str | int, ...]
Line = tuple[str, str]  # (`migrate`, `note`, or `manual`, the words after the file's name)
# The files that are JSON, by surface: edited a key at a time on its line, and read back as JSON.
JSON_SURFACES = ("sitemap",)


class Stays(Exception):
    """A name the engine leaves as it is, for this reason."""


def at(data: Any, path: Key) -> Any:
    for step in path:
        data = data[step]
    return data


class Block:
    """One piece of YAML or JSON in a file, with the data it should hold once the edits made to its text are done."""

    def __init__(self, rel: str, surface: str, text: str, span: tuple[int, int]) -> None:
        self.rel, self.surface, self.span, self.text = rel, surface, span, text
        self.data = self.parsed(text)
        self.lines: list[Line] = []

    def parsed(self, text: str) -> Any:
        """`text` read as its file's format: JSON for a JSON surface, else aidd's YAML. A DocumentError when it does not read as a mapping."""
        if self.surface not in JSON_SURFACES:
            return documents.parse_yaml(text, self.rel)
        try:
            data = json.loads(text)
        except (ValueError, RecursionError) as exc:
            raise documents.DocumentError(f"{self.rel}: {exc}") from None
        if not isinstance(data, dict):
            raise documents.DocumentError(f"{self.rel}: not a JSON object")
        return data

    def name(self, path: Key) -> str:
        """A key as a line shows it: its path, and for a handoff note, which note."""
        return ("handoff note " if self.surface == "handoff" else "") + retired_names.shown(path)

    def say(self, kind: str, words: str) -> None:
        self.lines.append((kind, f"{self.rel}: {words}"))

    def rename_key(self, path: Key, new: str) -> None:
        parent = at(self.data, path[:-1])
        if new in parent:
            raise Stays(retired_names.collision_problem(path, new))
        text = yaml_edit.rename_key(self.text, path, new)
        if text is None:
            raise Stays("it is not on a line of its own (a flow mapping, or a line shared with another key)")
        self.text = text
        items = list(parent.items())
        parent.clear()
        parent.update({(new if k == path[-1] else k): v for k, v in items})

    def cut(self, path: Key) -> Any:
        parent = at(self.data, path[:-1])
        text = yaml_edit.cut(self.text, path, parent_empty=len(parent) == 1)
        if text is None:
            raise Stays("it is not on a line of its own, or it is the only key of its list item")
        self.text = text
        return parent.pop(path[-1])

    def set_value(self, path: Key, value: Any) -> None:
        """The value of the key at `path`, written as `value` on its line."""
        text = yaml_edit.set_value(self.text, path, value)
        if text is None:
            raise Stays("its value is not on its line (a block, or a flow collection)")
        self.text = text
        at(self.data, path[:-1])[path[-1]] = value

    def set_list(self, path: Key, value: list) -> None:
        """The value of the key at `path`, a list in flow style on its line, written as `value`."""
        text = yaml_edit.set_list(self.text, path, value)
        if text is None:
            raise Stays("its list is not in flow style on its line, such as `[cost]`")
        self.text = text
        at(self.data, path[:-1])[path[-1]] = value

    def nest(self, key: str, outer: str, head: dict[str, Any]) -> None:
        """The top-level `key` moved into the one item of a new list `outer`, which starts with the `head` fields."""
        text = yaml_edit.nest(self.text, key, outer, head)
        if text is None:
            raise Stays("it is not a top-level key on a line of its own")
        self.text = text
        self.data[outer] = [{**head, key: self.data.pop(key)}]

    def append_items(self, key: str, items: list[dict]) -> None:
        """`items` at the end of the block list at the top-level `key`, which is made when it is missing. A list in flow style stays."""
        try:
            text = strict_yaml.append_items(self.text, key, items)
        except ValueError as exc:
            raise Stays(str(exc)) from None
        self.text = text if self.text.endswith("\n") else text.removesuffix("\n")
        self.data[key] = [*self.data.get(key, []), *items]

    def add(self, path: tuple[str, ...], value: Any) -> None:
        """A new key at the end of the top level, or `path[-1]` in the block mapping at `path[:-1]`."""
        try:
            text = yaml_edit.append_key(self.text, path[0], value) if len(path) == 1 else strict_yaml.set_entry(self.text, path[:-1], path[-1], value)
        except ValueError as exc:
            raise Stays(str(exc)) from None
        self.text = text if self.text.endswith("\n") else text.removesuffix("\n")  # a front matter's last line has no newline of its own
        parent = self.data
        for step in path[:-1]:
            parent = parent.setdefault(step, {})
        parent[path[-1]] = value

    def reads_back(self) -> bool:
        try:
            return self.parsed(self.text) == self.data
        except documents.DocumentError:
            return False
