"""A Spec, an Intent, a proposal, a runbook, or a postmortem in an earlier shape, read as today's in memory and never written (`aidd
upgrade` writes the file). A branch forked before an upgrade holds the old names on its base commit, and a check that decides by the
base (`testing.base_view`, the approved copy the delegate compares) must still read it, or an upgrade alone would look like the head
changing an approved Spec.
The rows of schemas/retired-names.json do the work: a rename moves the key, a cut drops it, and a move of a value is a function
here. `setup.migrating` reads each row through this module's `apply_row` before it edits the file, so the file it writes reads as
this module reads the old one, and a name it leaves for a person is refused here too (`retired_names.Refused`). Two facts go into
another file, which the reading of one file cannot hold: a `blocks` entry becomes the other item's `blocked_by`, and a team's
`intents` in the config becomes each Intent's `delivery_team`. Both only group and order the work list, and no check reads them."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aidd import config
from aidd.kernel import resources, retired_names

# The types read here: each work item and typed document with front matter of its own (schemas/item-types.json), each a surface
# of schemas/retired-names.json. A document in a work item's folder, such as an exploration, has a reader of its own.
SURFACES = tuple(t for t in config.types_of_form("work_item", "typed_document") if t not in config.types_with("inside_work_item"))


@dataclass
class Relations:
    """A Spec's old `relations` sorted by where each entry goes now: `blocked_by` (the ids it waits for), `blocks` (the ids that
    wait for it, which their own `blocked_by` holds), `parent` (the Intent it `implements`), and `left` (an entry with no place
    now, as a sentence, such as `duplicates SPEC-3`)."""

    blocked_by: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    parent: str | None = None
    left: list[str] = field(default_factory=list)


def sort_relations(relations: Any) -> Relations:
    """Where each entry of a Spec's old `relations` goes. A value that is no list of `{type, id}` mappings puts all of it in `left`."""
    if not isinstance(relations, list):
        return Relations(left=["relations is not a list"])
    out = Relations()
    for entry in relations:
        kind, other = (entry.get("type"), entry.get("id")) if isinstance(entry, dict) else (None, None)
        if not isinstance(other, str) or not other:
            out.left.append(f"an entry with no id: {entry!r}")
        elif kind == "blocked_by":
            out.blocked_by.append(other)
        elif kind == "blocks":
            out.blocks.append(other)
        elif kind == "implements" and out.parent in (None, other):
            out.parent = other
        else:
            out.left.append(f"{kind} {other}")
    out.blocked_by[:] = list(dict.fromkeys(out.blocked_by))
    out.blocks[:] = list(dict.fromkeys(out.blocks))
    return out


def sort_intent_relations(relations: Any) -> Relations:
    """Where each entry of an Intent's old `relations` goes: as a Spec's, but an Intent has no `parent`, so an `implements` entry
    has no place and joins `left`."""
    out = sort_relations(relations)
    if out.parent:
        out.left.append(f"implements {out.parent}")
        out.parent = None
    return out


def one_phase(title: Any, slices: Any) -> dict:
    """The phase an Intent's old `slices` list becomes: `P1`, named for the Intent (its title, cut to the 120 characters a name holds)."""
    name = title.strip()[:120] if isinstance(title, str) else ""
    return {"id": "P1", "name": name or "Phase 1", "slices": slices}


def last_slice(data: dict) -> str | None:
    """The id of the last slice of the last phase of an Intent in either shape (the old `slices` list is one phase), or None."""
    phases = data["phases"] if isinstance(data.get("phases"), list) else [{"slices": data.get("slices")}]
    found = phases[-1].get("slices") if phases and isinstance(phases[-1], dict) else None
    last = found[-1] if isinstance(found, list) and found else None
    return str(last["id"]) if isinstance(last, dict) and isinstance(last.get("id"), str) else None


def _into_risk(data: dict, path: retired_names.Path, key: str) -> None:
    """The value of the top-level key at `path` moved into the `risk` mapping as `key`. Refused when there is no `risk` mapping to
    hold it, or it holds `key` already."""
    risk = data.get("risk")
    if not isinstance(risk, dict):
        raise retired_names.Refused("the Spec has no `risk` block to hold it")
    if key in risk:
        raise retired_names.Refused(f"`risk.{key}` is set too, so remove one of the two by hand")
    risk[key] = data.pop(str(path[-1]))


def _experiment(data: dict, path: retired_names.Path) -> None:
    """An `experiment` is the tracking plan's now, so it is never moved or dropped."""
    raise retired_names.Refused("a Spec holds none now")


def _relations(data: dict, path: retired_names.Path) -> None:
    """`relations` becomes `blocked_by`, and a Spec's `implements` its `parent`. An entry with no place now, an `implements` that
    names another Intent than `parent` does, or a `blocked_by` that is no list is refused. A `blocks` entry is the other item's
    `blocked_by`, which the upgrade writes in that file."""
    intent = data.get("type") == "intent"
    found = (sort_intent_relations if intent else sort_relations)(data["relations"])
    held = data.get("blocked_by")
    if found.left:
        raise retired_names.Refused(f"{'; '.join(found.left)} has no place in {'an Intent' if intent else 'a Spec'} now")
    if found.parent and data.get("parent") not in (None, found.parent):
        raise retired_names.Refused(f"`implements {found.parent}` and `parent: {data['parent']}` both name an Intent")
    if found.blocked_by and held is not None and not isinstance(held, list):
        raise retired_names.Refused("`blocked_by` is set too, and it is no list to add to")
    del data["relations"]
    if found.blocked_by:
        data["blocked_by"] = list(dict.fromkeys([*(held or []), *found.blocked_by]))
    if found.parent and not data.get("parent"):
        data["parent"] = found.parent


def _slices(data: dict, path: retired_names.Path) -> None:
    if "phases" in data:
        raise retired_names.Refused("`phases` is set too, so merge the slices into a phase by hand")
    data["phases"] = [one_phase(data.get("title"), data.pop("slices"))]


def _context(data: dict, path: retired_names.Path) -> None:
    if not (isinstance(data["context"], str) and not data["context"].strip()):
        raise retired_names.Refused(
            "it holds a value, and the project glossary (`docs/GLOSSARY.md`) holds the terms every Spec shares: move it there, then remove `context`"
        )
    del data["context"]


def _launch(data: dict, path: retired_names.Path) -> None:
    value, last = data["launch"], last_slice(data)
    if value != last:
        raise retired_names.Refused(
            f"it names {retired_names.shown_value(value)}, and the last slice is {last}: put the launch slice last in its phase, then remove `launch`"
        )
    del data["launch"]


def irreversible_of(reversible: Any) -> bool | None:
    """`risk.irreversible` for a Spec's old `risk.reversible`: its opposite, so `reversible: false` is `irreversible: true`, and a
    Spec that left it out is reversible under either name. None for a value that is no boolean: a person moves it by hand. The one
    reading `aidd upgrade` and a commit before it share."""
    return (not reversible) if isinstance(reversible, bool) else None


def role_identity(identity: Any) -> str | None:
    """The `role:<role>` an identity in the shape before 1.0.0 names: `agent:<role>`, with no `/`, where `<role>` is a key of
    schemas/roles.json's roles, so `agent:developer` is `role:developer`. None for any other value, which stays as written: an
    `agent:<harness>/<model>`, a person, or an `agent:` name that is no role. The one reading `aidd upgrade` and a commit before it share."""
    if not isinstance(identity, str) or not identity.startswith("agent:"):
        return None
    role = identity.removeprefix("agent:")
    return f"role:{role}" if "/" not in role and role in resources.load_json("roles.json")["roles"] else None


# The type a Spec takes when none is given, as `aidd new spec` and `aidd risk` take it: a retired change type whose row names no
# `--change-type` becomes this one (tests/test_change_types.py holds it equal to the CLI's default).
DEFAULT_CHANGE_TYPE = "feat"


def change_type_of(change_type: Any) -> tuple[str, str | None] | None:
    """(the type, the risk dimension it adds or None) for a change type retired in 1.0.0, read from its `--change-type` row of
    schemas/retired-names.json, so `deps` is (`build`, None), `infra` is (`build`, `availability`), and `security` is
    (`feat`, `security`): a row that names no `--change-type` takes DEFAULT_CHANGE_TYPE. None for a type of today, or for any other
    value. The one reading `aidd upgrade` and a commit before it share, so a split into two facts reads the same in both."""
    if not isinstance(change_type, str):
        return None
    row = next((r for r in retired_names.rows("cli_value") if r["old"] == f"--change-type {change_type}"), None)
    if row is None:
        return None
    flags = row["new"].split()
    typed = dict(zip(flags[::2], flags[1::2], strict=True))
    return typed.get("--change-type", DEFAULT_CHANGE_TYPE), typed.get("--dimension")


def _change_type(data: dict, path: retired_names.Path) -> None:
    """A retired change type becomes its type, and its dimension joins `risk.dimensions`. Refused when the dimension has no list to
    join: no `risk` mapping, or a `risk.dimensions` that is no list."""
    moved = change_type_of(data["change_type"])
    if moved is None:
        return
    kind, dimension = moved
    if dimension is not None:
        risk = data.get("risk")
        held = risk.get("dimensions", []) if isinstance(risk, dict) else None
        if not isinstance(held, list) or not isinstance(risk, dict):
            raise retired_names.Refused(f"the Spec has no `risk.dimensions` list to hold `{dimension}`")
        if dimension not in held:
            risk["dimensions"] = [*held, dimension]
    data["change_type"] = kind


def _irreversible(data: dict, path: retired_names.Path) -> None:
    risk = data["risk"]
    flipped = irreversible_of(risk["reversible"])
    if flipped is None:
        raise retired_names.Refused(f"{retired_names.shown_value(risk['reversible'])} is no `true` or `false`, so its opposite is no value aidd can write")
    retired_names.apply_row(data, {"rule": "rename", "new": "risk.irreversible"}, path, {})
    risk["irreversible"] = flipped


def _role(data: dict, path: retired_names.Path) -> None:
    parent: Any = data
    for step in path[:-1]:
        parent = parent[step]
    if (role := role_identity(parent[path[-1]])) is not None:
        parent[path[-1]] = role


# What a `value` row does to the data, by the row's id.
_VALUES = {
    "intent-context": _context,
    "intent-launch": _launch,
    "intent-relations": _relations,
    "intent-slices": _slices,
    "spec-change-type": _change_type,
    "spec-cost-estimate": lambda data, path: _into_risk(data, path, "cost_estimate"),
    "spec-experiment": _experiment,
    "spec-relations": _relations,
    "spec-residual-risk": lambda data, path: _into_risk(data, path, "residual"),
    "spec-risk-reversible": _irreversible,
    "spec-suggested-by": _role,
    "spec-task-assignee": _role,
}


def apply_row(data: dict, row: retired_names.Row, path: retired_names.Path) -> None:
    """The place `path` names in the parsed front matter `data` of a type in SURFACES moved the way `row` says, in place: what `aidd
    upgrade` and `todays_shape` share. Raises `retired_names.Refused` where the upgrade leaves the name for a person."""
    retired_names.apply_row(data, row, path, _VALUES)


def todays_shape(raw: dict) -> dict:
    """`raw`, the front matter of a type in SURFACES, with every retired name moved to its replacement. Raises
    `retired_names.Refused` for a name the upgrade leaves for a person, such as an `experiment`, a new name set beside the old one,
    or a `risk.reversible` that is no boolean. Any other type comes back as it is."""
    kind = raw.get("type")
    return retired_names.todays_shape(raw, kind, _VALUES) if kind in SURFACES else raw


def explained(item_type: str, error: str, data: dict) -> str:
    """A schema error of the front matter `data`, with the row that retired the name or the value it names, and the step."""
    return retired_names.explain(item_type, error, data, _VALUES)
