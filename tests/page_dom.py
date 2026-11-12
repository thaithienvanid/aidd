"""A small document tree for the page tests: HTML text in, nodes out, with the standard library's parser.

A page test compares the markup with the status answer, so it needs the elements, their attributes, and their text. This is
not a browser: it never runs a script and never applies a style. `parse(html)` gives the root; `node.find_all(...)` finds
by tag and attribute; `node.text` is the text under a node with its whitespace folded to single spaces.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

VOID = {"meta", "img", "br", "hr", "input", "link", "area", "base", "col", "source", "wbr"}


class Node:
    def __init__(self, tag: str, attrs: dict[str, str | None], parent: Node | None = None):
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.children: list[Node | str] = []

    @property
    def text(self) -> str:
        parts = [c if isinstance(c, str) else c.text for c in self.children]
        return re.sub(r"\s+", " ", " ".join(parts)).strip()

    @property
    def raw_text(self) -> str:
        return "".join(c if isinstance(c, str) else c.raw_text for c in self.children)

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def find_all(self, tag: str | None = None, **attrs: str | bool) -> list[Node]:
        """Every node under this one with `tag` (any when None) and the attributes: a string must match exactly, True means
        the attribute is present. An underscore in a name stands for a hyphen (`data_item` is `data-item`)."""
        found = []
        for node in self.walk():
            if node is self or (tag and node.tag != tag):
                continue
            if all((key.replace("_", "-") in node.attrs) if want is True else node.attrs.get(key.replace("_", "-")) == want for key, want in attrs.items()):
                found.append(node)
        return found

    def find(self, tag: str | None = None, **attrs: str | bool) -> Node | None:
        return next(iter(self.find_all(tag, **attrs)), None)

    def get(self, name: str, default: str = "") -> str:
        value = self.attrs.get(name)
        return default if value is None else value


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {})
        self.at = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), self.at)
        self.at.children.append(node)
        if tag not in VOID:
            self.at = node

    def handle_endtag(self, tag):
        node = self.at
        while node is not self.root and node.tag != tag:
            node = node.parent or self.root
        if node is not self.root:
            self.at = node.parent or self.root

    def handle_data(self, data):
        self.at.children.append(data)


def parse(html: str) -> Node:
    builder = _Builder()
    builder.feed(html)
    builder.close()
    return builder.root
