"""The rows of `aidd upgrade` that move one key of a Spec into another key of the same Spec. They need only the Spec's own text, so
they sit apart from `migrating`, which reads the files and keeps the rows that need what a whole run knows."""

from __future__ import annotations

from aidd import workitems
from aidd.kernel import retired_names
from aidd.setup.migration_blocks import Block, Key, at


def design_into_docs(block: Block, path: Key) -> str:
    """`design.files` is cut, and each path becomes a `design-files` entry at the end of the block list `docs` (`workitems.design_entries`,
    the reading `workitems.apply_row` gave), which is made when the Spec has none; a `docs` in flow style stays for a person."""
    files = at(block.data, path)["files"]
    block.cut(path)
    block.append_items("docs", workitems.design_entries(files))
    return f"design.files {retired_names.shown_value(files)} -> docs entries of type design-files, frozen as they were"
