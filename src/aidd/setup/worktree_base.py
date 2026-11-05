"""Where a role's worktree starts. A harness whose roles run in worktrees may document a project setting that starts each
one from the current commit (`config.HARNESSES`, `worktree_base`), as Claude Code's `worktree.baseRef: "head"` does. Without
it, a role's worktree branches from the remote's default branch, so the role lacks the change's commits and its frozen tests,
and a lead would move it with `git reset --hard`, an `ask`, at every start.

Where the team's roles run in such a harness, `aidd init --aidd-team` and `aidd upgrade` write the setting into the harness's
project file, and `aidd doctor` notes when no settings file sets it. A value a file already holds, `"fresh"` or any other, is
the person's and stays. aidd lists what it wrote under `<harness>-worktree` in `.aidd/harness-rules.json`, so `aidd uninstall`
takes out only that, and only while it still holds aidd's value. The setting grants no permission and changes no ask, allow,
or deny rule.
"""

from __future__ import annotations

import json
from pathlib import Path

from aidd import config
from aidd.kernel import regular_files, resources
from aidd.setup import team_install

LEDGER_SUFFIX = "-worktree"  # the ledger key is `<harness>-worktree`, such as `claude-code-worktree`


def _so(source: str) -> str:
    return f"each role's worktree starts from your current commit and holds this change's commits and frozen tests, as {source} says"


def runs_roles(root: Path, key: str, wired: list[str], *, plugin: bool = False) -> bool:
    """Whether the delivery team's roles run in the harness `key` here: its role files are in the repository (or a plan holds
    them), or, for Claude Code while it is wired, the aidd-team plugin carries them (`plugin`: init installs it now)."""
    if key == "claude-code":
        # The project agents `team_install.team_files` writes for Claude Code, one for each role the team ships.
        roles = [f".claude/agents/{team_install.TEAM_PREFIX}{src.name}" for src in sorted((resources.data_dir("team") / "agents").glob("*.md"))]
        carried = key in wired and (plugin or team_install.team_plugin_carries_roles(root))
        return carried or any(regular_files.is_file_or_held(root, rel) for rel in roles)
    return any(regular_files.is_file_or_held(root, rel) for rel in team_install.harness_paths().get(key, ()))


def _read(root: Path, rel: str) -> tuple[dict | None, str]:
    """A JSON object file in the repository, {} when there is none, or None and why aidd leaves it as it is: a link, a pipe,
    or a device is never read and so never written through, and text that is no JSON object is never rewritten."""
    text, why = regular_files.named_text(root, rel)
    if text is None and why == regular_files.MISSING:
        return {}, ""
    if text is None:
        return None, f"it is {why}, which aidd never reads or writes through"
    try:
        data = json.loads(text)
    except ValueError:
        return None, "it is not valid JSON"
    return (data, "") if isinstance(data, dict) else (None, "it holds no JSON object")


def _place(data: dict, key: tuple[str, ...]) -> tuple[dict | None, object]:
    """The object that holds the setting's last step, made where it is missing, and the value there now (None when unset);
    (None, that value) when a step on the way holds something other than an object."""
    here = data
    for step in key[:-1]:
        nxt = here.setdefault(step, {})
        if not isinstance(nxt, dict):
            return None, nxt
        here = nxt
    return here, here.get(key[-1])


def _json(value: object) -> str:
    return json.dumps(value)[:80]


def _write(root: Path, rel: str, data: dict) -> None:
    """A settings or ledger file, through the safe writer: a link at it or on the way to it is refused, never written through."""
    regular_files.write_text_safely(root, root / rel, json.dumps(data, indent=2) + "\n")


def apply(root: Path, wired: list[str], *, plugin: bool = False, write: bool = True) -> list[str]:
    """Write each harness's worktree setting where the team's roles run there and its project file sets no value; what it
    wrote or kept, one line each. With `write` False it says what it would write and writes nothing."""
    out: list[str] = []
    for key, harness in config.HARNESSES.items():
        base = harness.worktree_base
        if base is None or not runs_roles(root, key, wired, plugin=plugin):
            continue
        dotted, by_hand = ".".join(base.key), f"add {base.shown()} to {base.file} by hand, so {_so(base.source)}"
        data, why = _read(root, base.file)
        ledger, ledger_why = _read(root, config.HARNESS_RULES_FILE)
        if data is None or ledger is None:
            out.append(f"kept     {base.file} ({why or f'{config.HARNESS_RULES_FILE}: {ledger_why}'}, so aidd leaves it as it is: {by_hand})")
            continue
        there = regular_files.is_file_or_held(root, base.file)
        holder, now = _place(data, base.key)
        if holder is None:
            out.append(
                f"kept     {base.file} (its `{base.key[0]}` holds {_json(now)}, not an object, so aidd leaves it as it is: set `{base.key[0]}` "
                f"to {base.shown(1)} by hand, so {_so(base.source)})"
            )
            continue
        if now is not None:
            if now != base.value:
                out.append(
                    f"kept     {base.file} (it sets {dotted} to {_json(now)}, your own value, which aidd never changes; "
                    f"with {_json(base.value)}, {_so(base.source)})"
                )
            continue
        holder[base.key[-1]] = base.value
        verb = ("updated " if there else "wrote   ") if write else ("would update" if there else "would write")
        out.append(f"{verb} {base.file} ({dotted} {_json(base.value)}: {_so(base.source)}; it grants no permission and changes no ask rule)")
        if write:
            _write(root, base.file, data)
            _write(root, config.HARNESS_RULES_FILE, {**ledger, key + LEDGER_SUFFIX: [dotted]})
    return out


def doctor_lines(root: Path, wired: list[str]) -> list[tuple[str, str]]:
    """What `aidd doctor` notes: for each harness whose team roles run here and whose settings files set no worktree setting,
    the line to add and why. Silent where a file sets it, to any value, since a set value is the person's choice."""
    out: list[tuple[str, str]] = []
    for key, harness in config.HARNESSES.items():
        base = harness.worktree_base
        if base is None or not runs_roles(root, key, wired):
            continue
        paths = config.claude_settings_paths(root) if key == "claude-code" else [root / base.file]
        if any(_is_set(root, path, base.key) for path in paths):
            continue
        out.append(
            (
                "info",
                f"{harness.label}: the delivery team's roles run in worktrees, and no settings file sets `{'.'.join(base.key)}`, so each role's "
                f"worktree starts from the remote's default branch and lacks this change's commits and frozen tests. Add {base.shown()} to "
                f"{base.file}, or run `aidd upgrade --yes`, which adds it ({base.source})",
            )
        )
    return out


def _is_set(root: Path, path: Path, key: tuple[str, ...]) -> bool:
    """Whether the settings file at `path`, in the repository or the person's own, gives the setting any value."""
    try:
        here = json.loads(regular_files.text_at(root, path) or "")
    except ValueError:
        return False
    for step in key:
        if not isinstance(here, dict) or step not in here:
            return False
        here = here[step]
    return True


def remove(root: Path, *, write: bool = True) -> list[str]:
    """`aidd uninstall`: take out each worktree setting the ledger says aidd wrote, while it still holds aidd's value; a value
    a person changed since stays. What it did, one line each."""
    ledger, _why = _read(root, config.HARNESS_RULES_FILE)
    out: list[str] = []
    for key, harness in config.HARNESSES.items():
        base = harness.worktree_base
        if base is None or not ledger or key + LEDGER_SUFFIX not in ledger:
            continue
        dotted, listed = ".".join(base.key), ledger[key + LEDGER_SUFFIX]
        data, why = _read(root, base.file)
        holder, now = _place(data, base.key) if data else (None, None)
        if not isinstance(listed, list) or dotted not in listed:  # the ledger is data: only a list that names the key claims it
            out.append(f"kept     {base.file} ({dotted}: {config.HARNESS_RULES_FILE} does not list it as aidd's, so aidd leaves it as it is)")
        elif data is None or holder is None or now != base.value:
            reason = why or ("it holds no such setting now" if now is None else f"it holds {_json(now)} now, a value of yours")
            out.append(f"kept     {base.file} ({dotted}: {reason}, so aidd leaves it as it is)")
        else:
            out.append(f"{'removed ' if write else 'would remove'} {dotted} from {base.file} (aidd wrote it)")
            del holder[base.key[-1]]
            _drop_empty(data, base.key[:-1])
            if write:
                _write(root, base.file, data)
        if write:
            ledger = {k: v for k, v in ledger.items() if k != key + LEDGER_SUFFIX}
            if ledger:
                _write(root, config.HARNESS_RULES_FILE, ledger)
            else:
                (root / config.HARNESS_RULES_FILE).unlink()
    return out


def _drop_empty(data: dict, steps: tuple[str, ...]) -> None:
    """Remove each object on the setting's way that taking it out left empty, the deepest first."""
    for depth in range(len(steps), 0, -1):
        parent = data
        for step in steps[: depth - 1]:
            parent = parent[step]
        if parent.get(steps[depth - 1]) == {}:
            del parent[steps[depth - 1]]
