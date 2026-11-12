"""One piece of a file that `aidd upgrade` edits (setup.migrating): its text, the data it should hold once the edits made to its text
are done, and the edits, one key at a time (kernel.yaml_edit)."""

from __future__ import annotations

from typing import Any

from aidd.kernel import documents, retired_names, yaml_edit

Key = tuple[str | int, ...]
Line = tuple[str, str]  # (`migrate`, `note`, or `manual`, the words after the file's name)


class Stays(Exception):
    """A name the engine leaves as it is, for this reason."""


def at(data: Any, path: Key) -> Any:
    for step in path:
        data = data[step]
    return data


class Block:
    """One piece of YAML in a file, with the data it should hold once the edits made to its text are done."""

    def __init__(self, rel: str, surface: str, text: str, span: tuple[int, int]) -> None:
        self.rel, self.surface, self.span, self.text = rel, surface, span, text
        self.data = self.parsed(text)
        self.lines: list[Line] = []

    def parsed(self, text: str) -> Any:
        """`text` read as aidd's YAML. A DocumentError when it does not read as a mapping."""
        return documents.parse_yaml(text, self.rel)

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

    def reads_back(self) -> bool:
        try:
            return self.parsed(self.text) == self.data
        except documents.DocumentError:
            return False
