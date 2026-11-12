"""A Spec, an Intent, a proposal, a runbook, or a postmortem in an earlier shape, read as today's in memory and never written (`aidd
upgrade` writes the file). A branch forked before an upgrade holds the old names on its base commit, and a check that decides by the
base (`testing.base_view`, the approved copy the delegate compares) must still read it, or an upgrade alone would look like the head
changing an approved Spec.
The rows of schemas/retired-names.json do the work: a rename moves the key, a cut drops it, and a move of a value is a function
here, by the row's id (`_VALUES`). `setup.migrating` reads each row through this module's `apply_row` before it edits the file, so
the file it writes reads as this module reads the old one, and a name it leaves for a person is refused here too
(`retired_names.Refused`)."""

from __future__ import annotations

from collections.abc import Callable

from aidd import config
from aidd.kernel import retired_names

# The types read here: each work item and typed document with front matter of its own (schemas/item-types.json), each a surface
# of schemas/retired-names.json. A document in a work item's folder, such as an exploration, has a reader of its own.
SURFACES = tuple(t for t in config.types_of_form("work_item", "typed_document") if t not in config.types_with("inside_work_item"))

# What a `value` row does to the data, by the row's id. Release 1.0.0 has no such row: the first one added later brings its function here
# (`retired_names.apply_row` raises for a `value` row with none).
_VALUES: dict[str, Callable[[dict, retired_names.Path], None]] = {}


def apply_row(data: dict, row: retired_names.Row, path: retired_names.Path) -> None:
    """The place `path` names in the parsed front matter `data` of a type in SURFACES moved the way `row` says, in place: what `aidd
    upgrade` and `todays_shape` share. Raises `retired_names.Refused` where the upgrade leaves the name for a person."""
    retired_names.apply_row(data, row, path, _VALUES)


def todays_shape(raw: dict) -> dict:
    """`raw`, the front matter of a type in SURFACES, with every retired name moved to its replacement. Raises
    `retired_names.Refused` for a name the upgrade leaves for a person, such as a new name set beside the old one. Any other type
    comes back as it is."""
    kind = raw.get("type")
    return retired_names.todays_shape(raw, kind, _VALUES) if kind in SURFACES else raw


def explained(item_type: str, error: str, data: dict) -> str:
    """A schema error of the front matter `data`, with the row that retired the name or the value it names, and the step."""
    return retired_names.explain(item_type, error, data, _VALUES)
