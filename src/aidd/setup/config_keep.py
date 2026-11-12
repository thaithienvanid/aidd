"""`aidd init --force` and the config: every value a person set stays. The config is the one file init never regenerates,
because it holds a person's decisions. `--force` changes only the values a flag given on this run sets, each listed as a
line of output; every other line stays as it is, comments and keys init never writes included. If a value could not stay,
the run is refused before it writes anything."""

from __future__ import annotations

import copy
import re
from typing import Any

from aidd.config import CONFIG_PATH
from aidd.kernel import documents, strict_yaml


def _whole(path: tuple[str, ...]):
    """A flag that gives one whole value: it sets the value at `path` and nothing around it."""
    return lambda old, fresh: {path: v} if (v := _get(fresh, path)) is not None else {}


def _each_key(path: tuple[str, ...]):
    """A flag that gives a mapping of values: each key it names is set, and every other key in the old mapping stays."""
    return lambda old, fresh: {(*path, k): v for k, v in (_get(fresh, path) or {}).items()}


def _union(path: tuple[str, ...]):
    """A flag that names items to add to a list: the old items stay, and the new ones join them."""

    def resolve(old: Any, fresh: Any) -> dict:
        now, given = _get(old, path), _get(fresh, path)
        if given is None:
            return {}
        return {path: [*now, *(i for i in given if i not in now)] if isinstance(now, list) else given}

    return resolve


def _entries(path: tuple[str, ...], key: str, only: tuple[str, ...] = ()):
    """A flag that gives list entries, each named by `key`: an old entry of the same name takes the new value of the fields in
    `only` (all its fields when empty), and the other fields and entries stay. An empty list says there are none."""

    def resolve(old: Any, fresh: Any) -> dict:
        now, given = _get(old, path), _get(fresh, path)
        if given is None:
            return {}
        if not isinstance(now, list) or not given:
            return {path: given}
        merged = copy.deepcopy(now)
        for entry in given:
            at = next((i for i, e in enumerate(merged) if isinstance(e, dict) and e.get(key) == entry.get(key)), None)
            if at is None:
                merged.append(entry)
            else:
                merged[at].update({k: v for k, v in entry.items() if not only or k in only})
        return {path: merged}

    return resolve


def _delegation(old: Any, fresh: Any) -> dict:
    """`--delegate` writes the block when there is none. A block that is there stays as it is: a renewal (`set_by`,
    `review_due`) is a person's own edit, never a side effect, so an expired delegation does not come back."""
    now, given = _get(old, ("delegation",)), _get(fresh, ("delegation",))
    return {("delegation",): given} if given is not None and not isinstance(now, dict) else {}


def _environments(old: Any, fresh: Any) -> dict:
    """`--environment` and `--own-environment` set the environments they name. `--environment none` does not drop environments that
    are listed: without them, a delegated merge could pass where it deferred before, which is looser, so a person removes them."""
    now, given = _get(old, ("environments",)), _get(fresh, ("environments",))
    if given == [] and isinstance(now, list) and now:
        names = ", ".join(str(e.get("name")) for e in now if isinstance(e, dict))
        raise ValueError(
            f"--environment none would drop the environments {CONFIG_PATH} lists ({names}), and without them a delegated merge could pass where it deferred before. "
            "Nothing was written. If nothing deploys now, remove `environments` from the file by hand, then run again"
        )
    return _entries(("environments",), "name")(old, fresh)


# The option that sets each config value: how it sets it (given the old config and the one init generates, the paths it sets
# and their values) and what a person types.
SETS = {
    "profile": (_whole(("profile",)), "--profile"),
    "approvers": (_whole(("owners", "approvers")), "--approvers"),
    "specialists": (_each_key(("owners", "specialists")), "--specialist"),
    "test": (_entries(("tests",), "name", only=("command",)), "--test"),
    "environments": (_environments, "--environment or --own-environment"),
    "delegate": (_delegation, "--delegate"),
    "compliance_targets": (_union(("project", "compliance", "targets")), "--compliance-target"),
}


def given(options: Any) -> list[str]:
    """The options a flag set on this run, by `SETS` name: those `options.given` names, or, with none named, each that holds
    a value (`environments` holds one when it is `[]`, which says nothing deploys)."""
    if options.given is not None:
        return [n for n in SETS if n in options.given]
    held = {"environments": options.environments is not None, "delegate": options.delegate, "compliance_targets": bool(options.compliance_targets)}
    return [n for n in SETS if held.get(n, getattr(options, n, None) is not None)]


def keep_flagged(old_text: str, fresh_text: str, names: list[str]) -> tuple[str, list[str]]:
    """`keep_values` for the options `names` set, each with the value it sets in the config init generates (`fresh_text`)
    and in the config there is now: a flag that names one pool, one test, or one environment sets that one."""
    try:
        old = documents.parse_yaml(old_text, CONFIG_PATH)
    except documents.DocumentError as exc:
        raise refusal(str(exc)) from None
    fresh = documents.parse_yaml(fresh_text, CONFIG_PATH)
    sets: dict[tuple[str, ...], tuple[Any, str]] = {}
    for name in names:
        resolve, flag = SETS[name]
        sets |= {path: (value, flag) for path, value in resolve(old, fresh).items()}
    text, lines = keep_values(old_text, sets)
    kept = _get(old, ("delegation",))
    if "delegate" in names and isinstance(kept, dict):
        lines.insert(
            0,
            f"config   kept    delegation as it is, set by {kept.get('set_by')} until {kept.get('review_due')} (--delegate); renew it by editing `review_due`",
        )
    return text, lines


def _get(data: Any, path: tuple[str, ...]) -> Any:
    for step in path:
        if not isinstance(data, dict) or step not in data:
            return None
        data = data[step]
    return data


def _put(data: dict, path: tuple[str, ...], value: Any) -> None:
    for step in path[:-1]:
        nested = data.get(step)
        if not isinstance(nested, dict):
            nested = data[step] = {}
        data = nested
    data[path[-1]] = value


def _leaves(data: Any, prefix: tuple = ()) -> dict[tuple, Any]:
    """Every value of a document by its path: a scalar or a list is one leaf; an empty mapping, too."""
    if isinstance(data, dict) and data:
        return {k: v for key, value in data.items() for k, v in _leaves(value, (*prefix, key)).items()}
    return {prefix: data}


def _shown(value: Any) -> str:
    return strict_yaml.flow(value)


def _named(value: Any) -> dict[str, Any] | None:
    """A list of entries that each have a name, by name; None for any other value."""
    if isinstance(value, list) and value and all(isinstance(e, dict) and isinstance(e.get("name"), str) for e in value):
        return {e["name"]: e for e in value}
    return None


def _change_lines(shown: str, was: Any, value: Any, flag: str) -> list[str]:
    """The lines for one value that changed, each shown in full. A list of named entries (`tests`, `environments`) gets a
    line for each entry that changed or went, and none for an entry that stayed."""
    old, new = _named(was), _named(value)
    if old is None or new is None:
        if was is None:
            return [f"config   added   {shown}: {_shown(value)} ({flag})"]
        return [f"config   changed {shown}: {_shown(was)} -> {_shown(value)} ({flag})"]
    lines = [
        f"config   added   {shown}.{name}: {_shown(entry)} ({flag})"
        if name not in old
        else f"config   changed {shown}.{name}: {_shown(old[name])} -> {_shown(entry)} ({flag})"
        for name, entry in new.items()
        if old.get(name) != entry
    ]
    return lines + [f"config   dropped {shown}.{name}: {_shown(entry)} ({flag})" for name, entry in old.items() if name not in new]


def _scalar_line(text: str, key: str, value: Any) -> str | None:
    """`text` with the top-level `key: old` line holding `value`, its trailing comment kept; None when no such line is there."""
    pattern = re.compile(rf"^({re.escape(key)}:[ ]*)(\"[^\"\n]*\"|'[^'\n]*'|[^\s#]+)(.*)$", re.M)
    if not pattern.search(text):
        return None
    return pattern.sub(lambda m: f"{m.group(1)}{strict_yaml.scalar(value)}{m.group(3)}", text, count=1)


def _block(text: str, key: str, value: Any) -> tuple[str, bool]:
    """`text` with the top-level `key` holding `value`, and whether it rewrote a block: a scalar changes on its own line and
    keeps its comment, and a block is replaced where it is (the comments inside it go), or added at the end."""
    if not isinstance(value, (dict, list)) and (done := _scalar_line(text, key, value)) is not None:
        return done, False
    return strict_yaml.set_block(text, key, value), True


def refusal(why: str) -> ValueError:
    return ValueError(
        f"--force cannot keep the values in {CONFIG_PATH}: {why}. Nothing was written. Fix the file, or move it aside and run `aidd init` again to write a new one"
    )


def keep_values(old_text: str, sets: dict[tuple[str, ...], tuple[Any, str]]) -> tuple[str, list[str]]:
    """The config `--force` leaves over `old_text`, and a line for each value that changed or comment that went. `sets` is
    each config path a flag sets, with the value the flag gives and its words (`SETS`). The old text stays as it is except
    the top-level blocks a flag changes. A ValueError (`refusal`) when the old text does not parse, or a value outside
    `sets` would not read back as it was."""
    try:
        old = documents.parse_yaml(old_text, CONFIG_PATH)
    except documents.DocumentError as exc:
        raise refusal(str(exc)) from None
    new = copy.deepcopy(old)
    lines: list[str] = []
    touched: list[str] = []
    for path, (value, flag) in sets.items():
        was = _get(old, path)
        if was == value:
            continue
        _put(new, path, value)
        lines += _change_lines(".".join(path), was, value, flag)
        touched.append(path[0])
    text, rewrote = old_text, []
    for key in dict.fromkeys(touched):
        text, block = _block(text, key, new[key])
        rewrote += [key] if block else []
    try:
        read_back = documents.parse_yaml(text, CONFIG_PATH)
    except documents.DocumentError as exc:
        raise refusal(f"the result does not read back ({exc})") from None
    moved = {p for p, v in _leaves(read_back).items() if _leaves(old).get(p, _MISSING) != v} | {p for p in _leaves(old) if p not in _leaves(read_back)}
    unset = [".".join(p) for p in sorted(moved) if not any(p[: len(s)] == s for s in sets)]
    if read_back != new or unset:
        raise refusal(f"{', '.join(unset) or 'a value'} would not stay as it is")
    gone = [c for c in old_text.splitlines() if c.lstrip().startswith("#") and c not in text.splitlines()]
    lines += [f"config   dropped the comment `{c.strip()}` inside {', '.join(rewrote)}, which a flag rewrote" for c in gone]
    return text, lines


_MISSING = object()
