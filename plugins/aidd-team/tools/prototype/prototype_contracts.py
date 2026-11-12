"""Component contracts and Storybook index matching for the prototype tool."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

FORMAT = 1
_VOID = frozenset("area base br col embed hr img input link meta source track wbr".split())


class _Parts(HTMLParser):
    """Each `data-component` a design names: its variant, the screen it sits on, and its test id."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[tuple[str, str, str, str]] = []  # (component, variant, screen, test id)
        self._screens: list[tuple[int, str]] = []  # (depth, screen), while inside one
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in reversed(attrs)}
        if tag not in _VOID:
            self._depth += 1
        if tag == "section" and a.get("data-screen"):
            self._screens.append((self._depth, a["data-screen"]))
        if a.get("data-component"):
            screen = self._screens[-1][1] if self._screens else ""
            self.found.append((a["data-component"], a.get("data-variant") or "default", screen, a.get("data-testid", "")))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID:
            return
        if self._screens and self._screens[-1][0] == self._depth and tag == "section":
            self._screens.pop()
        self._depth = max(0, self._depth - 1)


def component_contract(parts: list[str]) -> dict:
    """The contract of the design `parts` (markup, as assembled): each component's variants, the screens that use it
    (none: the chrome, on every screen), and its test ids, sorted, so the same design always gives the same file."""
    found: dict[str, dict[str, set[str]]] = {}
    for part in parts:
        reader = _Parts()
        reader.feed(part)
        reader.close()
        for name, variant, screen, testid in reader.found:
            entry = found.setdefault(name, {"variants": set(), "screens": set(), "testids": set()})
            entry["variants"].add(variant)
            if screen:
                entry["screens"].add(screen)
            if testid:
                entry["testids"].add(testid)
    return {"schema_version": str(FORMAT), "components": [{"name": name, **{k: sorted(v) for k, v in entry.items()}} for name, entry in sorted(found.items())]}


def kebab(text: str) -> str:
    """A name as the contract writes it: `NoteCard` and `Note card` are `note-card`."""
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", text).lower()).strip("-")


def stories_of(index: object) -> set[tuple[str, str]]:
    """Each story in Storybook's `index.json` (version 4 and later: `entries`; version 3: `stories`) as (component,
    variant): the last part of its title and its name, kebab-cased, so `Components/NoteCard` / `Compact` is
    (`note-card`, `compact`). A story with no title or name falls back to its id, `<title>--<name>`."""
    if not isinstance(index, dict):
        raise ValueError("it holds no JSON object")
    entries = index["entries"] if "entries" in index else index.get("stories", {})
    if not isinstance(entries, dict):
        raise ValueError("its entries are no JSON object")
    found = set()
    for key, entry in entries.items():
        if not isinstance(entry, dict) or entry.get("type", "story") != "story":
            continue
        title, _, name = str(entry.get("id", key)).partition("--")
        found.add((kebab(str(entry.get("title") or title).split("/")[-1]), kebab(str(entry.get("name") or name))))
    return found


def missing_stories(contract: dict, stories: set[tuple[str, str]]) -> list[str]:
    """Each component variant with no story of its own: a story whose title ends with the component's name and whose
    name is the variant (`Components/NoteCard`, `Compact` for `note-card` / `compact`)."""
    return [
        f"component `{c['name']}` has no story for its `{variant}` variant: add one titled `.../{c['name']}` (or set the CSF `title` so it ends so) and named `{variant}`"
        for c in contract["components"]
        for variant in c["variants"]
        if (c["name"], variant) not in stories
    ]


def contract_of(tool: Any, root: Path, rel: str | None, docs_dir: str = "docs") -> tuple[dict | None, list[str]]:
    """The component contract of a prototype file or the product prototype.

    Single files check structural viewer validity (so frozen specs with non-structural lint remain readable);
    the product prototype enforces full product and design checks."""
    if rel:
        _, problems = tool.view_prototype_file(root, rel, write=False)
        if problems:
            return None, [*problems, f"fix {rel} first: a contract is read only from a design with no problem"]
        found = tool._PRODUCT.search((root / rel).read_text(encoding="utf-8"))
        assert found is not None
        return component_contract([found.group(2)]), []
    sitemap, shell, flows, problems = tool.load(root, docs_dir)
    if sitemap and shell:
        problems += tool._product_design_problems(sitemap, shell, flows, root / docs_dir / tool.APP)[0]
    if not sitemap or not shell or problems:
        return None, [*problems, f"fix {docs_dir}/{tool.APP}/ first: a contract is read only from a design with no problem"]
    return component_contract([tool.product_body(sitemap, shell, flows)]), []
