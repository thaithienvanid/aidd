"""A config in an earlier shape, read as today's in memory and never written (`aidd upgrade` writes the file). The base commit of
a branch forked before an upgrade holds the old names, and the checks that decide by the base (`testing.base_view`) must still
read it, or the change would be checked by its own head. The rows of schemas/retired-names.json do the work: a rename moves the
key, a cut drops it, and a few moves of a value are functions here. `setup.migrating` reads each row through this module's
`apply_row` before it edits the file, so the file it writes reads as this module reads the old one, and a name it leaves for a
person is refused here too (`retired_names.Refused`)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aidd.kernel import globs, retired_names, strict_yaml

# The document types `docs.required` knew by another name, and the reason `docs.disabled` gives for a type that was `off`.
DOC_TYPES_RENAMED = {"analytics": "tracking-plan", "authz": "authz-matrix", "compliance": "compliance-record", "migration": "migration-plan"}
DISABLED_REASON = "set off before aidd 1.0.0 as docs.required"


def disabled_types(required: dict, disabled: dict) -> dict[str, str]:
    """The `docs.disabled` entries that `docs.required` held: each type that was `off`, under its new name, unless `disabled` names it already."""
    return {DOC_TYPES_RENAMED.get(t, t): DISABLED_REASON for t, level in required.items() if level == "off" and DOC_TYPES_RENAMED.get(t, t) not in disabled}


def _at(data: Any, path: retired_names.Path) -> Any:
    for step in path:
        data = data[step]
    return data


def _docs_required(data: dict, path: retired_names.Path) -> None:
    docs = _at(data, path[:-1])
    required, disabled = docs["required"], docs.get("disabled")
    if not isinstance(required, dict) or any(v not in ("off", "warn") for v in required.values()):
        raise retired_names.Refused("a type holds a value but `off` or `warn`")
    if disabled is not None and not isinstance(disabled, dict):
        raise retired_names.Refused("`docs.disabled` is no mapping of types")
    del docs["required"]
    if added := disabled_types(required, disabled or {}):
        docs["disabled"] = {**(disabled or {}), **added}


def _rule_check(data: dict, path: retired_names.Path) -> None:
    rule, value = _at(data, path[:-1]), _at(data, path)
    names = {t.get("name") for t in data.get("tests") or [] if isinstance(t, dict)}
    if not isinstance(value, str) or value not in names:
        raise retired_names.Refused(f"{strict_yaml.flow(value)} is no name in `tests`: add the command as a `tests` entry, then list its name in `enforced_by`")
    retired_names.apply_row(data, {"rule": "rename", "new": "enforced_by"}, path, {})
    rule["enforced_by"] = [value]


def _intents(data: dict, path: retired_names.Path) -> None:
    ids = _at(data, path)
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise retired_names.Refused("it is not a list of Intent ids")
    del _at(data, path[:-1])[path[-1]]  # each Intent it lists gets the team in its own file, which the upgrade writes there


def deploying_environments(data: dict) -> list[str]:
    """The names of the `environments` of the parsed config `data` whose `branches` list the default branch that `delegation.default_branch`
    names, by the rule the risk rules use for a push (`globs.ref_matches`). Empty when the config names no default branch, or no list holds it."""
    delegation, environments = data.get("delegation"), data.get("environments")
    branch = delegation.get("default_branch") if isinstance(delegation, dict) else None
    if not isinstance(branch, str) or not branch or not isinstance(environments, list):
        return []
    named = [e for e in environments if isinstance(e, dict) and isinstance(e.get("branches"), list)]
    try:
        return [str(e.get("name")) for e in named if any(isinstance(p, str) and globs.ref_matches(p, branch) for p in e["branches"])]
    except globs.GlobError:  # a name too long to match is no proof that the branch is listed
        return []


def _default_branch_deploys(data: dict, path: retired_names.Path) -> None:
    """`delegation.default_branch_deploys` is cut when it says `false`, which holds back nothing. `true` said a merge into the default branch
    deploys, so it is cut only when an `environments` entry of this config lists that branch: else the config would say less than the
    person did, and a delegated merge could pass. Any other value is refused."""
    delegation, value = _at(data, path[:-1]), _at(data, path)
    if value is True and not deploying_environments(data):
        raise retired_names.Refused(
            "it says a merge into the default branch deploys, and no `environments` entry lists that branch. Set `delegation.default_branch` to its name,"
            " list it in an entry's `branches`, then remove `delegation.default_branch_deploys`"
        )
    if value is not True and value is not False:
        raise retired_names.Refused(f"{retired_names.shown_value(value)} is no `true` or `false`")
    del delegation[path[-1]]


# What a `value` row does to the data, by the row's id.
_VALUES: dict[str, Callable[[dict, retired_names.Path], None]] = {
    "delegation-default-branch-deploys": _default_branch_deploys,
    "delivery-team-intents": _intents,
    "docs-required": _docs_required,
    "project-rule-check": _rule_check,
}


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
