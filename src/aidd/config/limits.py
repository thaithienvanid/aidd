"""The limits: named numbers that change what aidd decides or shows. `config.schema.json` owns each one, with its default, its
range, and whether a project may lower it, raise it, or set it either way (`x-project-may`). Code and text read the default
from the schema and never restate it. A number outside its range fails the config's load, with the range and the next step.

A limit that guards a control has its default as the ceiling or the floor, so a project can only make it stricter; a limit
that decides nothing (a count of lines shown, a cadence) takes any value in its range."""

from __future__ import annotations

import functools
import re
from typing import Any

from aidd.kernel import json_schema, resources

SCHEMA = "config.schema.json"
GROUP = "limits"
# `x-project-may`: which way a project may move a limit from its default.
LOWER, RAISE, ANY = "lower", "raise", "any"
_ERROR = re.compile(r"^\$\.limits\.([a-z_]+(?:\.[a-z_]+)?): (.*)$")
_TURNS = re.compile(r"^(\$\.agents\.max_turns\.[^:\s]+): (.*)$")


def schema_node(path: str) -> dict:
    """The config schema's property at the dotted `path` (`limits.max_task_retries`, `docs.max_review_age_days`). A name on the way
    that holds a list of mappings, such as `tests`, continues into the list's items, and into the definition they refer to."""
    node = resources.load_json(SCHEMA)
    for key in path.split("."):
        if node.get("type") == "array":
            node = json_schema.deref(node["items"], SCHEMA)[0]
        if "allOf" in node:
            node = json_schema.deref(next(part for part in node["allOf"] if "$ref" in part), SCHEMA)[0]
        node = json_schema.deref(node["properties"][key], SCHEMA)[0]
    return node


def setting_default(path: str) -> Any:
    """The default the schema gives the config key at `path`. A key with none is a defect, so this raises KeyError."""
    return schema_node(path)["default"]


@functools.cache
def names() -> tuple[str, ...]:
    """Every limit as its dotted name inside `limits`, in the schema's order (`retrospective_every.days`)."""

    def walk(node: dict, prefix: str) -> list[str]:
        out: list[str] = []
        for name, sub in node["properties"].items():
            out += walk(sub, f"{prefix}{name}.") if sub.get("type") == "object" else [f"{prefix}{name}"]
        return out

    return tuple(walk(schema_node(GROUP), ""))


def may(name: str) -> str:
    """Which way a project may move the limit `name` from its default: `lower`, `raise`, or `any`."""
    return schema_node(f"{GROUP}.{name}")["x-project-may"]


def allowed(name: str) -> str:
    """The range of the limit `name` and who may move it, in words: `1 to 3, and a project may only lower it`."""
    node = schema_node(f"{GROUP}.{name}")
    rule = {LOWER: ", and a project may only lower it", RAISE: ", and a project may only raise it", ANY: ""}[node["x-project-may"]]
    return f"{node['minimum']} to {node['maximum']}{rule}"


def explain(error: str) -> str | None:
    """A schema error at a limit (a `limits` member or an `agents.max_turns` entry), said with the range and the next step; None for any other error."""
    if turns := _TURNS.match(error):
        bound = json_schema.deref(schema_node("agents.max_turns")["additionalProperties"], SCHEMA)[0]
        return f"{turns.group(1)}: {turns.group(2)}. It takes {bound['minimum']} to {bound['maximum']} turns, and {bound['maximum']} is the most aidd ships for any role. Remove the line to use the role's own number"
    found = _ERROR.match(error)
    if not found or found.group(1) not in names():
        return None
    name, why = found.groups()
    return f"$.{GROUP}.{name}: {why}. It takes {allowed(name)}. Remove the line to use the default, {setting_default(f'{GROUP}.{name}')}"


def merged(parent: dict | None, child: dict, base: str = "") -> dict:
    """A child config's limits over its parent's. A limit a project may only lower keeps the lower of the two, one it may only raise
    keeps the higher, and any other takes the child's, so a child never loosens the limit a parent set."""
    out = dict(parent or {})
    for key, value in child.items():
        name = f"{base}{key}"
        if isinstance(value, dict):
            out[key] = merged(out.get(key), value, f"{name}.")
        elif key in out and may(name) in (LOWER, RAISE):
            out[key] = (min if may(name) == LOWER else max)(out[key], value)
        else:
            out[key] = value
    return out
