"""The files one run of `aidd upgrade` reads, and what the run shares across them: the config and each parent it extends from the
repository, the work items and the typed documents that have front matter, and the edited copies of library standards. Each file is a
`Source`: its text, and the blocks of YAML in it that the rows of schemas/retired-names.json apply to (`migrating`)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from aidd import config, workitems
from aidd.kernel import documents, globs, regular_files
from aidd.setup.migration_blocks import Block as _Block
from aidd.setup.migration_blocks import Line

# The fence of a handoff note in a work item (workitems.handoff_notes owns the note's format).
HANDOFF = re.compile(r"^```aidd-handoff[ \t]*\r?\n(.*?)^```[ \t]*$", re.S | re.M)
# The front matter types whose retired names the engine moves, each its own surface of schemas/retired-names.json.
TYPE_SURFACE = {t: t for t in config.types_of_form("work_item", "typed_document")}


@dataclass
class Ctx:
    """What one run shares across files and gives the function of each `value` row. No row shares anything across files now: the first
    row that writes into a file other than its own adds the fields it needs."""


class Source:
    """A file that holds blocks of YAML: its text, and each block's place in it."""

    def __init__(self, rel: str, text: str) -> None:
        self.rel, self.text = rel, text
        self.blocks: list[_Block] = []

    def add(self, surface: str, span: tuple[int, int]) -> None:
        raw = self.text[span[0] : span[1]]
        try:
            self.blocks.append(_Block(self.rel, surface, raw.replace("\r\n", "\n"), span))
        except documents.DocumentError:
            pass  # not YAML aidd reads: `aidd validate` names it

    def rendered(self) -> str:
        """The file with each changed block in place. A block that cannot be written whole stays as it was, with a `manual` line."""
        out, last = [], 0
        for block in self.blocks:
            if not any(kind == "migrate" for kind, _ in block.lines):
                continue
            raw = self.text[block.span[0] : block.span[1]]
            mixed = "\r\n" in raw and re.search(r"(?<!\r)\n", raw)
            if mixed or not block.reads_back():
                why = (
                    "it mixes two kinds of line ending: make them one kind"
                    if mixed
                    else "the edit did not read back as the data it should hold: make the changes by hand"
                )
                block.lines = [(k, w) for k, w in block.lines if k != "migrate"]
                block.say("manual", f"not changed, because {why}. Then run `aidd upgrade` again; `aidd validate` names each retired name")
                continue
            out += [self.text[last : block.span[0]], block.text.replace("\n", "\r\n") if "\r\n" in raw else block.text]
            last = block.span[1]
        return "".join([*out, self.text[last:]])


def _read(root: Path, rel: str) -> str | None:
    text = regular_files.repository_text(root, rel, documents.MAX_DOCUMENT_BYTES)
    return None if text is None or "�" in text or text.startswith("﻿") else text


def config_sources(root: Path, lines: list[Line]) -> list[Source]:
    """The config, and each parent it extends from the repository (a remote parent is only named)."""
    out: list[Source] = []
    queue, seen = [(config.CONFIG_PATH, 0)], set()
    while queue:
        rel, depth = queue.pop(0)
        if rel in seen or (text := _read(root, rel)) is None:
            continue
        seen.add(rel)
        source = Source(rel, text)
        source.add("config", (0, len(text)))
        if not source.blocks:
            if rel == config.CONFIG_PATH:
                try:
                    documents.parse_yaml(text, rel)
                except documents.DocumentError as exc:  # a config aidd cannot read stops the upgrade, naming its line
                    raise ValueError(f"{exc}. Fix that line, then run `aidd upgrade` again") from None
            continue
        out.append(source)
        for parent in source.blocks[0].data.get("extends") or []:
            if isinstance(parent, dict) and isinstance(parent.get("path"), str) and depth < 5:
                queue.append((parent["path"], depth + 1))
            elif isinstance(parent, dict) and isinstance(parent.get("url"), str):
                lines.append(
                    (
                        "note",
                        f"{rel}: the parent {documents.one_line(parent['url'], 100)} is remote, so aidd reads and moves nothing in it: if it holds a retired name, its owner moves it",
                    )
                )
    return out


def item_sources(root: Path, specs_dir: str, proposals_dir: str, product_dir: str) -> list[Source]:
    """The work items under the specs and proposals folders and the Intents' folder, and the runbooks and postmortems in theirs
    (`workitems.OPS_DIRS`): each one's front matter by its type, and each handoff note in it."""
    out: list[Source] = []
    work = workitems.work_folders(specs_dir, product_dir)
    folders = list(dict.fromkeys([*work, proposals_dir, *workitems.OPS_DIRS.values()]))
    paths = {p for d in folders for p in workitems.object_files(root, d)}
    paths |= {p for d in work if (root / d).is_dir() for p in (root / d).rglob("exploration.md")}
    for path in sorted(paths):
        rel = path.relative_to(root).as_posix()
        if (text := _read(root, rel)) is None:
            continue
        source = Source(rel, text)
        if front := documents.FRONT_MATTER.match(text):
            try:
                kind = str(documents.parse_yaml(front.group(1), rel).get("type"))
            except documents.DocumentError:
                kind = ""
            if kind in TYPE_SURFACE:
                source.add(TYPE_SURFACE[kind], front.span(1))
        for note in HANDOFF.finditer(text):
            source.add("handoff", note.span(1))
        out.append(source)
    return out


def copy_sources(root: Path, main: dict) -> list[Source]:
    """The edited copies of library standards that the config lists, each one's front matter. An unedited copy is not here:
    `aidd upgrade` writes it again from the library, in today's shape."""
    from aidd import knowledge

    folder = globs.under(globs.normal_dir(str((main.get("docs") or {}).get("dir") or "docs")), "standards/")
    library = knowledge.standards_library()
    out: list[Source] = []
    for entry in main.get("standards") or []:
        recorded = entry.get("from_library") if isinstance(entry, dict) else None
        if not isinstance(recorded, dict):
            continue
        rel = entry.get("path")
        if not isinstance(rel, str) or not rel.startswith(folder) or any(s.rel == rel for s in out) or (text := _read(root, rel)) is None:
            continue
        front = documents.FRONT_MATTER.match(text)
        if front and knowledge.copy_edited(text, recorded, library.get(str(recorded.get("id")))):
            source = Source(rel, text)
            source.add("standard", front.span(1))
            out.append(source)
    return out
