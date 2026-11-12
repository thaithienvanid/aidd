"""What aidd knows about each type of thing it tracks or writes (`schemas/item-types.json`): a work item, a document a Spec
links, a document the repository has one of. One row for each type, so another type is a row and no code that lists types.
Each fact is read when first asked, never on import. Who owns a document and whether it is frozen or living stay in
`loop.documents` of schemas/roles.json, and each format stays in its own schema."""

from __future__ import annotations

import functools

from aidd.kernel import resources

# What a row's `folder` or `files` path says when `loop.documents` of schemas/roles.json gives the one path.
ROLES_HOME = "<loop.documents>"


@functools.cache
def _table() -> dict:
    return resources.load_json("item-types.json")


def item_type_rows() -> dict[str, dict]:
    """Every type's row, keyed by the type, in the order `aidd new` lists them."""
    return _table()["types"]


def item_type_groups() -> dict[str, str]:
    """The groups `aidd new --list` prints, by key, each with the words it prints, in its order."""
    return _table()["groups"]


def common_documents() -> tuple[str, ...]:
    """The documents `aidd new --help` names after the work items, in its order."""
    return tuple(_table()["common_documents"])


def types_with(fact: str) -> tuple[str, ...]:
    """The types whose row states `fact` and does not say false, in the rows' order."""
    return tuple(name for name, row in item_type_rows().items() if row.get(fact))


def types_with_field(field: str) -> tuple[str, ...]:
    """The types whose schema has a field named `field`, in the rows' order. A schema is the one owner of its fields, so no row
    says which types take one, and a type with no schema takes none."""
    return tuple(name for name, row in item_type_rows().items() if "schema" in row and field in resources.load_json(row["schema"]).get("properties", {}))


def types_in(group: str) -> tuple[str, ...]:
    """The types of one group, in the rows' order."""
    return tuple(name for name, row in item_type_rows().items() if row["group"] == group)


def types_of_form(*forms: str) -> tuple[str, ...]:
    """The types of the forms named, in the rows' order: `work_item`, `typed_document`, `document`."""
    return tuple(name for name, row in item_type_rows().items() if row["form"] in forms)


def status_table(item_type: str) -> dict:
    """The schema node that holds the status words of `item_type` (`enum`, `x-meanings`, `x-groups`, and the facts about
    them: `x-initial`, `x-sets`, `x-transitions`), or {} when its row names none."""
    pointer = item_type_rows()[item_type].get("statuses")
    if not pointer:
        return {}
    schema_file, _, path = pointer.partition("#")
    node = resources.load_json(schema_file)
    for part in path.strip("/").split("/"):
        node = node[part]
    return node


class StatusSet(frozenset):
    """Statuses that code asks about a stored value. A value that is no word, such as a list written where a status goes, is in
    no set, so a check reads it as a status that is none of these, and the schema's finding for it still comes."""

    def __contains__(self, value: object) -> bool:
        try:
            return super().__contains__(value)
        except TypeError:
            return False


def status_set(item_type: str, name: str) -> frozenset[str]:
    """The statuses of `item_type` in its status table's set `name` (`x-sets`): a fact about them that code reads."""
    return StatusSet(status_table(item_type)["x-sets"][name]["statuses"])


def status_transitions(item_type: str) -> list[dict]:
    """Each move of `item_type`'s status (`x-transitions`: `from`, `to`, `by`, `when`, `requires`), in the table's order."""
    return list(status_table(item_type)["x-transitions"])


def initial_status(item_type: str) -> str:
    """The status a new item of `item_type` starts in (`x-initial`)."""
    return str(status_table(item_type)["x-initial"]["status"])
