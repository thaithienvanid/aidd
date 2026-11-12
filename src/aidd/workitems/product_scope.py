"""The product scope as aidd reads it: the files in the product folder (`product_dir`), the items they hold, and the status
each item derives from its latest result.

The four files are the BRD, the PRD, the standing outcomes, and the intent order (`schemas/product-scope.schema.json`). The
first three hold items (objectives, requirements, and product outcomes), each with an id, and the intent order ranks the
Intents. An item stores no status: its latest result gives `met` or `retired`, else `active`. The files that exist give the
shape of the product scope. Intents live beside them and are read as every other Intent is, never here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from aidd import config
from aidd.kernel import documents, timestamps
from aidd.workitems import intent_paths, objects, spec_file

# The type of the file that orders the Intents, and the types of the files that hold items: the rest of the group.
ORDER = "intent-order"
HOLDING = tuple(t for t in config.types_in("product_scope") if t != ORDER)
# Each list of items in a file's front matter, and the type of item it holds.
LISTS = (("objectives", "objective"), ("requirements", "requirement"), ("outcomes", "outcome"))
ACTIVE, MET, RETIRED = "active", "met", "retired"
# What a `decision` of a result makes an item.
BY_DECISION = {"met": MET, "retire": RETIRED}


@dataclass(frozen=True)
class Item:
    """One objective, requirement, or product outcome: its id, its type, the type of the file that holds it, its title, the id it
    serves (empty for none), and its status, derived from its latest result."""

    id: str
    type: str
    file_type: str
    title: str
    serves: str
    status: str


@dataclass
class ProductFile:
    """A file of the product scope that exists: its type, its path from the repository's top, its front matter, its body,
    and whether it read whole (`readable`, with its schema errors empty in `problems`)."""

    type: str
    path: str
    data: dict = field(default_factory=dict)
    body: str = ""
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    misfiled: bool = False

    @property
    def readable(self) -> bool:
        return not self.problems


@dataclass
class ProductScope:
    """The product scope of a repository: the files of each type that exist, the items the readable ones hold, and an id
    held twice as (id, first path, second path). `exists` is whether a file that holds items does."""

    files: dict[str, ProductFile] = field(default_factory=dict)
    items: dict[str, Item] = field(default_factory=dict)
    repeated: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def exists(self) -> bool:
        return any(t in self.files for t in HOLDING)

    @property
    def whole(self) -> bool:
        """Whether every file that holds items read, so an id that resolves nowhere is a mistake, and no file left it out."""
        return all(f.readable for t, f in self.files.items() if t in HOLDING)

    @property
    def order(self) -> list[str]:
        """The Intent ids of the intent order, first to last; empty with no order or an unreadable one."""
        found = self.files.get(ORDER)
        ordered = found.data.get("order") if found is not None and found.readable else None
        return [str(i) for i in ordered] if isinstance(ordered, list) else []


def result_status(results: object) -> str:
    """The status a list of results gives: its latest by `measured_on` decides, `met` or `retired` from its `decision`, and
    anything else, or no result, is `active`. Entries on one day count in the order written, so the last one decides."""
    latest, decision = -1, ""
    for r in results if isinstance(results, list) else []:
        if isinstance(r, dict):
            day = timestamps.parse_date(r.get("measured_on"))
            if (n := day.toordinal() if day is not None else 0) >= latest:
                latest, decision = n, str(r.get("decision"))
    return BY_DECISION.get(decision, ACTIVE)


def items_of(data: dict, file_type: str) -> list[Item]:
    """The items one file's front matter holds, in the order it lists them. An entry of the wrong shape is left out: the
    schema names it."""
    found = []
    for key, item_type in LISTS:
        listed = data.get(key)
        for entry in listed if isinstance(listed, list) else []:
            if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                serves = entry.get("serves")
                found.append(
                    Item(
                        entry["id"],
                        item_type,
                        file_type,
                        str(entry.get("title") or ""),
                        serves if isinstance(serves, str) else "",
                        result_status(entry.get("results")),
                    )
                )
    return found


def read_file(root: Path, rel: str, item_type: str) -> ProductFile | None:
    """The file at `rel`, or None when it is not there, or when its front matter names no type of the product scope: other tools
    write `type:` too, so such a file is left alone, as `objects` leaves every file alone that names no aidd type. A type of the
    product scope in the wrong file is a problem. A file that does not parse or fails its schema comes back with its problems
    (as `aidd validate` words them) and no data, and its warnings stay with it."""
    if not os.path.lexists(root / rel):
        return None
    text, why = objects.read_document(root, rel)
    if text is None:
        return ProductFile(item_type, rel, problems=[f"{rel}: {why}"])
    declared = objects.front_line_in(iter(text.splitlines(keepends=True)))
    if declared is None or declared[1] not in (*HOLDING, ORDER):
        return None
    try:
        data, body, errors = spec_file.load_object(text, rel)
    except documents.DocumentError as exc:
        return ProductFile(item_type, rel, problems=[str(exc)])
    if data.get("type") != item_type:
        return ProductFile(item_type, rel, problems=[f"{rel}: type must be {item_type}, as the file's name says"], misfiled=True)
    problems = [e for e in errors if not e.startswith("warning: ")]
    return ProductFile(item_type, rel, {} if problems else data, body, problems, [e for e in errors if e.startswith("warning: ")])


def read(root: Path, product_dir: str) -> ProductScope:
    """The product scope in `product_dir`: each of its files that exists, and the items the readable ones hold. It reads
    the four files by name, never the folder, so the Intents that sit beside them are never mistaken for it."""
    scope = ProductScope()
    for item_type in (*HOLDING, ORDER):
        found = read_file(root, intent_paths.product_file(item_type, product_dir), item_type)
        if found is None:
            continue
        scope.files[item_type] = found
        if not found.readable:
            continue
        for item in items_of(found.data, item_type):
            if item.id in scope.items:
                scope.repeated.append((item.id, path_of(scope, item.id), found.path))
            else:
                scope.items[item.id] = item
    return scope


def path_of(scope: ProductScope, item_id: str) -> str:
    """The path from the repository's top of the file that holds the item `item_id`."""
    return scope.files[scope.items[item_id].file_type].path
