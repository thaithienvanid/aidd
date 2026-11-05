"""The names aidd retired (schemas/retired-names.json): which rows apply to a path in a file, and the sentence a loader adds
to an error for an old name. Nothing here knows a file's format. A path is a tuple of keys (str) and list positions (int), and
a row's path is a pattern over it: `name[]` is each item of the list at `name`, and `*` is any key."""

from __future__ import annotations

import copy
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from aidd.kernel import documents, resources, secret_patterns, strict_yaml

Row = dict[str, Any]
Path = tuple[str | int, ...]

_ERROR_AT = re.compile(r"^\$([^:]*): unknown field '(.*?)'")
_STEP = re.compile(r"\.([^.\[\]]+)|\[(\d+)\]")
_RANK = {"rename": 0, "read_both": 0, "value": 1, "cut": 2}  # a `read_both` row reads a name in place, as a rename does


def rows(surface: str | None = None) -> list[Row]:
    """The rows of the table, in its order; only those of `surface` when it is given."""
    return [r for r in resources.load_json("retired-names.json")["retired"] if surface is None or r["surface"] == surface]


def pattern_steps(pattern: str) -> list[tuple[str, bool]]:
    """A row's path as (key or `*`, whether the value there is a list whose every item is meant)."""
    return [(part.removesuffix("[]"), part.endswith("[]")) for part in pattern.split(".")]


def paths_in(data: Any, pattern: str) -> list[Path]:
    """Each place in `data` that `pattern` names, as the path of its last key, in document order. A place is named only where
    the key is there: a pattern with no match in `data` gives none."""
    found: list[Path] = []

    def walk(node: Any, steps: list[tuple[str, bool]], at: Path) -> None:
        if not steps or not isinstance(node, dict):
            return
        (key, each), rest = steps[0], steps[1:]
        for name in [k for k in node if key in ("*", k)]:
            here = (*at, name)
            if not rest and not each:
                found.append(here)
            elif each and isinstance(node[name], list):
                for i, item in enumerate(node[name]):
                    if rest:
                        walk(item, rest, (*here, i))
            elif rest:
                walk(node[name], rest, here)

    walk(data, pattern_steps(pattern), ())
    return found


def shown(path: Sequence[str | int]) -> str:
    """A path as a person reads it: `project.rules[0].level`."""
    return "".join(f"[{p}]" if isinstance(p, int) else (f".{p}" if i else p) for i, p in enumerate(path))


def _same(pattern: str, path: Path) -> bool:
    flat: list[str] = []
    for key, each in pattern_steps(pattern):
        flat.append(key)
        if each:
            flat.append("[]")
    have: list[str] = []
    for step in path:
        have.append("[]" if isinstance(step, int) else step)
    return len(flat) == len(have) and all(a in ("*", b) for a, b in zip(flat, have, strict=True))


def row_for(surface: str, path: Path) -> Row | None:
    """The row of `surface` whose old name is the place `path` names, or None."""
    return next((r for r in rows(surface) if _same(r["old"], path)), None)


def error_path(error: str) -> Path | None:
    """The path of the unknown key a schema error names (`$.project.rules[0]: unknown field 'level'`), or None for any other error."""
    found = _ERROR_AT.match(error)
    if not found:
        return None
    steps = [m.group(1) if m.group(1) is not None else int(m.group(2)) for m in _STEP.finditer(found.group(1))]
    return (*steps, found.group(2))


# A refusal is a sentence with the step in it, so it gets more room than a value does.
REFUSAL_CHARS = 600


def _refusal(exc: Exception) -> str:
    """A refusal's text as a loader's message shows it. A refusal may quote the value the file holds, which is the repository's text:
    each credential in it is hidden and it stays on one line, by the rule `shown_value` keeps for a value."""
    return documents.one_line(secret_patterns.scrubbed(str(exc)), REFUSAL_CHARS)


def explain(surface: str, error: str, data: Any = None, values: Mapping[str, Callable[[dict, Path], None]] | None = None) -> str:
    """`error`, a schema error of a file of `surface`, and when it names a retired key, the sentence that says what replaced it
    and how `aidd upgrade --yes` moves it, in place of the guess at a close name. With the file's `data` (and the `values` its
    rows' functions are), two more errors name their row: a value a `value` row moves, such as a retired change type, and a
    missing key that an old name beside it holds under the name a rename retired."""
    path = error_path(error)
    row = row_for(surface, path) if path else None
    head = _ERROR_AT.match(error)
    if path is None or row is None or head is None:
        return _explain_value(surface, error, data, values or {}) or _explain_missing(surface, error, data) or error
    was = f"`{shown(path)}` was retired in {row['retired_in']}"
    if row["rule"] == "rename":
        said = f"{was}; it is now `{row['new'].rsplit('.', 1)[-1].removesuffix('[]')}`. `aidd upgrade --yes` renames it"
    else:
        said = f"{was}. {row['note']} `aidd upgrade --yes` {'removes it' if row['rule'] == 'cut' else 'moves it'}"
        if row["rule"] == "value" and isinstance(data, dict) and row["id"] in (values or {}):
            try:
                apply_row(copy.deepcopy(data), row, path, values or {})
            except Refused as exc:  # the upgrade leaves it, so the sentence must not say it moves it
                said = f"{was}. {row['note']} `aidd upgrade --yes` leaves this one for a person: {_refusal(exc)}"
            except (KeyError, IndexError, TypeError, AttributeError):
                pass
    return f"{error[: head.end()]}. {said}"


_VALUE_ERROR_AT = re.compile(r"^\$([^:]*): must be one of ")
_MISSING_AT = re.compile(r"^\$([^:]*): missing required field '(.*?)'")


def _steps_of(shown_path: str) -> Path:
    return tuple(m.group(1) if m.group(1) is not None else int(m.group(2)) for m in _STEP.finditer(shown_path))


def _node(data: Any, path: Path) -> Any:
    """The value at `path` in `data`, or None where the path leads nowhere."""
    for step in path:
        if not isinstance(data, (dict, list)):
            return None
        try:
            data = data[step]  # type: ignore[index]
        except (KeyError, IndexError, TypeError):
            return None
    return data


def _explain_value(surface: str, error: str, data: Any, values: Mapping[str, Callable[[dict, Path], None]]) -> str | None:
    """The sentence for a value error at a key whose `value` row moves the value the file holds there, or None. A value the row
    leaves as it is, such as a typo, keeps the error alone."""
    found = _VALUE_ERROR_AT.match(error)
    path = _steps_of(found.group(1)) if found and isinstance(data, dict) else None
    row = row_for(surface, path) if path else None
    if path is None or row is None or row["rule"] != "value" or row["old"] != row["new"] or row["id"] not in values:
        return None
    moved = copy.deepcopy(data)
    try:
        apply_row(moved, row, path, values)
    except Refused as exc:
        return f"{error}. {row['note']} `aidd upgrade --yes` leaves this one for a person: {_refusal(exc)}"
    except (KeyError, IndexError, TypeError, AttributeError):
        return None
    if moved == data:
        return None
    was = f"`{shown(path)}: {shown_value(_node(data, path))}` was retired in {row['retired_in']}"
    return f"{error}. {was}. {row['note']} `aidd upgrade --yes` moves it"


def _explain_missing(surface: str, error: str, data: Any) -> str | None:
    """The sentence for a missing key that a key beside it holds under the name a rename row retired, or None."""
    found = _MISSING_AT.match(error)
    parent = _steps_of(found.group(1)) if found else ()
    holder = _node(data, parent) if found else None
    if found is None or not isinstance(holder, dict):
        return None
    for old in holder:
        row = row_for(surface, (*parent, old))
        if row and row["rule"] == "rename" and row["new"].rsplit(".", 1)[-1].removesuffix("[]") == found.group(2):
            return f"{error}. `{shown((*parent, old))}` holds it under the name retired in {row['retired_in']}: `aidd upgrade --yes` renames it"
    return None


def standard_renames() -> dict[str, str]:
    """Each library standard id that was renamed, with its new id: the `standard_id` rows."""
    return {r["old"]: r["new"] for r in rows("standard_id") if r["new"]}


def shown_value(value: Any) -> str:
    """A value as a line or a refusal shows it, with each credential in it hidden before the value is shortened, so no part of one is left."""
    return documents.one_line(secret_patterns.scrubbed(strict_yaml.flow(value)), 120)


class Refused(ValueError):
    """A place a retired name stands that its row cannot move from the data alone: a new name set beside the old one, or a
    value the row has no place for. `aidd upgrade` leaves the file as it is there and names the step, and a reader of an
    earlier shape refuses the same input with the same reason, so it never guesses a reading the upgrade would not write."""


def collision_problem(path: Path, new: str) -> str:
    """Why the key at `path` cannot become `new`: its mapping holds `new` already."""
    return f"`{shown((*path[:-1], new))}` is set too, so remove one of the two by hand"


def steps(data: Any, surface: str) -> list[tuple[Row, Path]]:
    """Each place in `data` a row of `surface` names, in the order they apply: renames, the deepest first, and the names read
    both ways, then moves of a value, then cuts, so a key renamed inside a list is renamed before a row moves the list. The places
    are found once, in the data as it was: `aidd upgrade` and the readers of an earlier shape walk this one list."""
    found = [(row, path) for row in rows(surface) for path in paths_in(data, row["old"])]
    return sorted(found, key=lambda step: (_RANK[step[0]["rule"]], -len(step[1]) if step[0]["rule"] == "rename" else 0))


def apply_row(data: Any, row: Row, path: Path, values: Mapping[str, Callable[[dict, Path], None]]) -> None:
    """The place `path` names in `data` moved the way `row` says, in place: the one function `aidd upgrade` and the readers of an
    earlier shape share for a row. A rename keeps the key where it stands. A `read_both` row reads an old value it lists in
    `read_as` as the new one, and an old key as the new key. A `value` row runs the function in `values` with its id. Raises
    `Refused` where the row has no place for it."""
    parent = data
    for step in path[:-1]:
        parent = parent[step]
    old = path[-1]
    if row["rule"] == "read_both" and "read_as" in row:
        here = parent[old]
        parent[old] = row["read_as"].get(here, here) if isinstance(here, str) else here
    elif row["rule"] in ("rename", "read_both"):
        new = row["new"].rsplit(".", 1)[-1].removesuffix("[]")
        if new in parent:
            raise Refused(collision_problem(path, new))
        items = list(parent.items())
        parent.clear()
        parent.update({(new if k == old else k): v for k, v in items})
    elif row["rule"] == "cut":
        if len(path) > 1 and isinstance(path[-2], int) and len(parent) == 1:
            raise Refused("it is the only key of its list item, which would hold nothing")
        parent.pop(old)
    elif row["id"] in values:
        values[row["id"]](data, path)
    else:  # a reader that misses a row would read its files as refused, and nothing would say why
        raise RuntimeError(f"no function reads the `value` row {row['id']}: add one where the other rows of its surface are read")


def todays_shape(raw: dict, surface: str, values: Mapping[str, Callable[[dict, Path], None]]) -> dict:
    """`raw`, a parsed file of `surface`, with every retired name moved to its replacement (`apply_row`, over `steps`), as a copy.
    Raises `Refused` for the first place the upgrade would leave as it is, so a caller treats the file as one it cannot read."""
    data = copy.deepcopy(raw)
    for row, path in steps(data, surface):
        try:
            apply_row(data, row, path, values)
        except (KeyError, IndexError, TypeError, AttributeError):
            raise Refused(PLACE_PROBLEM) from None
    return data


# Why a row's place is not there once an earlier row moved the data around it.
PLACE_PROBLEM = "its place in the file is not what the row expects"
