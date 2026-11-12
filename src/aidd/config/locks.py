"""`locks`: a parent config's list of what its children may not set. An item is a key (`docs`), which locks the whole key,
or a path to one member (`docs.disabled`, `owners.specialists.security`), which locks that member alone. The schema owns
which keys are lockable (`config.schema.json`, `locks`); this module checks each path against it and drops a locked member
from a child before the child merges."""

from __future__ import annotations

import copy
import difflib
import functools
from collections.abc import Iterable
from typing import Any

from aidd.kernel import json_schema, resources

SCHEMA = "config.schema.json"
# `project` is lockable, but its lock tightens only (config/project.py), so it takes no member path.
WHOLE_ONLY = "project"


@functools.cache
def lockable() -> tuple[str, ...]:
    """The keys a parent may lock, in the schema's order."""
    items = resources.load_json(SCHEMA)["properties"]["locks"]["items"]
    return tuple(items["anyOf"][0]["enum"])


def _members(node: dict, base: str, path: str, out: list[str]) -> None:
    """Add `path` and the path of every member under it that a lock can name: groups and their named members, never a
    key a person chooses (that key is free), and never inside a list."""
    node, base = json_schema.deref(node, base)
    out.append(path)
    if node.get("type") == "object" and not isinstance(node.get("additionalProperties"), dict):
        for name, sub in node.get("properties", {}).items():
            _members(sub, base, f"{path}.{name}", out)


@functools.cache
def paths() -> tuple[str, ...]:
    """Every path a lock can name: the lockable keys and the members of each, in the schema's order."""
    props = resources.load_json(SCHEMA)["properties"]
    out: list[str] = []
    for key in lockable():
        if key == WHOLE_ONLY:
            out.append(key)
        else:
            _members(props[key], SCHEMA, key, out)
    return tuple(out)


def _walk(lock: str) -> tuple[str, str | None] | None:
    """None when `lock` names a member, else why it does not and the lock to write instead (None when no fix is known).
    A key a person chooses (a pool, a model's tier) is any name."""
    key, *rest = lock.split(".")
    props = resources.load_json(SCHEMA)["properties"]
    if key not in lockable():
        return "is not a key a parent can lock", None
    if rest and key == WHOLE_ONLY:
        return f"names a member of `{key}`, which locks only as a whole and only tightens", key
    node, base, at = props[key], SCHEMA, key
    for part in rest:
        node, base = json_schema.deref(node, base)
        if node.get("type") == "array":
            return f"names a member of `{at}`, which is a list, so a lock holds all of it", at
        extra = node.get("additionalProperties")
        if not part:
            return f"has an empty member name after `{at}`", None
        if part in node.get("properties", {}):
            node = node["properties"][part]
        elif isinstance(extra, dict):
            node = extra
        else:
            return f"names no member of `{at}`", None
        at = f"{at}.{part}"
    return None


def problems(raw: dict) -> list[tuple[str, str]]:
    """(schema path, message) for each lock of `raw` that names nothing the schema has, with the lock to write instead or
    the closest path."""
    out = []
    locks = raw.get("locks")
    for i, lock in enumerate(locks if isinstance(locks, list) else []):
        found = _walk(lock) if isinstance(lock, str) else None
        if found is None:
            continue
        why, fix = found
        close = [fix] if fix else difflib.get_close_matches(lock, paths(), n=1, cutoff=0.6)
        hint = f"; write `{close[0]}`" if fix else f"; did you mean `{close[0]}`" if close else ""
        out.append(
            (
                f"$.locks[{i}]",
                f"$.locks[{i}]: {lock!r} {why}{hint}. A lock names a key ({', '.join(lockable())}), or one member of a key as `key.member`, such as `docs.disabled`.",
            )
        )
    return out


def without_locked(key: str, value: Any, locks: Iterable[str], where: str, warnings: list[str]) -> Any:
    """A child's `value` for `key` with each member a parent's member lock names taken out, and a warning for each."""
    mine = [lock.split(".")[1:] for lock in locks if lock.startswith(f"{key}.")]
    if not mine or not isinstance(value, dict):
        return value
    out = copy.deepcopy(value)
    for parts in mine:
        node: object = out
        for part in parts[:-1]:
            node = node.get(part) if isinstance(node, dict) else None
        if isinstance(node, dict) and parts[-1] in node:
            del node[parts[-1]]
            warnings.append(f"{where}: {key}.{'.'.join(parts)} is locked by a parent config and is ignored")
    return out
