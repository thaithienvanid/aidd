"""A config in an earlier shape, read as today's in memory and never written (`aidd upgrade` writes the file). The base commit of
a branch forked before an upgrade holds the old names, and the checks that decide by the base (`testing.base_view`) must still
read it, or the change would be checked by its own head. The rows of schemas/retired-names.json do the work: a rename moves the
key, a cut drops it, and a move of a value is a function here, by the row's id (`_VALUES`). `setup.migrating` reads each row through this module's
`apply_row` before it edits the file, so the file it writes reads as this module reads the old one, and a name it leaves for a
person is refused here too (`retired_names.Refused`)."""

from __future__ import annotations

from collections.abc import Callable

from aidd.kernel import retired_names, strict_yaml

# What a `value` row does to the data, by the row's id. Release 1.0.0 has no such row: the first one added later brings its function here
# (`retired_names.apply_row` raises for a `value` row with none).
_VALUES: dict[str, Callable[[dict, retired_names.Path], None]] = {}


def apply_row(data: dict, row: retired_names.Row, path: retired_names.Path) -> None:
    """The place `path` names in the parsed config `data` moved the way `row` says, in place: what `aidd upgrade` and
    `todays_shape` share. Raises `retired_names.Refused` where the upgrade leaves the name for a person."""
    retired_names.apply_row(data, row, path, _VALUES)


def explain(error: str, raw: dict) -> str:
    """`error`, a schema error of the parsed config `raw`, with the sentence for a retired name it names: what replaced it, and what `aidd upgrade --yes` does."""
    return retired_names.explain("config", error, raw, _VALUES)


def todays_shape(raw: dict) -> dict:
    """`raw`, a parsed config, with every retired name moved to its replacement. Raises `retired_names.Refused` for a name the
    upgrade leaves for a person: a new name set beside the old one, or a value no row has a place for."""
    return retired_names.todays_shape(raw, "config", _VALUES)


def in_todays_shape(text: str) -> str:
    """The config `text` as today's shape reads it, or `text` itself when it holds no retired name, does not parse, or holds a
    name the upgrade leaves for a person: then the load that follows fails at that name, as the head's would, and never reads a
    guess. The result is plain YAML without the comments, for a read and never for a file."""
    try:
        raw = strict_yaml.load(text.replace("\r\n", "\n"))
        moved = todays_shape(raw)
    except (strict_yaml.YamlError, retired_names.Refused):
        return text
    return strict_yaml.dump(moved) if moved != raw else text
