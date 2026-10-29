"""The test sections of a manifest a Spec freezes by itself: `pyproject.toml#tool.pytest`,
`package.json#scripts.test`. Spec approval then covers the section's content, not the whole file, so a dependency bump
never voids an approval, while an edit of the frozen section after it does; the gate warns when a change edits a test
section no Spec freezes (gate/rules/route.gate_harness).
"""

from __future__ import annotations

import json
import re

# The manifests whose test settings a Spec may freeze by section in tests.files, as `<path>#<dotted key>`:
# `pyproject.toml#tool.pytest`, `package.json#scripts.test`. The rest of the file, its dependencies, stays free, so a
# dependency bump never voids an approval, while an edit of the frozen section after Spec approval does.
SECTION_MANIFESTS = {"pyproject.toml": "toml", "package.json": "json"}
# The test sections `aidd new spec` freezes when a manifest has them.
TEST_SECTIONS = {
    "pyproject.toml": ("tool.pytest", "tool.coverage", "tool.tox", "project.entry-points.pytest11"),
    "package.json": ("scripts.test", "jest", "vitest", "mocha", "c8", "nyc"),
}
_SECTION_KEY = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_:-]+)*$")
_UNREADABLE = object()


def frozen_section(entry: str) -> tuple[str, str] | None:
    """(manifest path, dotted key) of a tests.files entry that names a section, or None for a path or a glob."""
    path, sep, key = entry.partition("#")
    return (path, key) if sep else None


def section_problem(entry: str) -> str | None:
    """Why a tests.files section entry is not one aidd can freeze, or None. Its path is exact and repo-relative (no `./`,
    `..`, leading `/`, backslash, empty part, or glob), so the gate and the hash read the file a person approved."""
    found = frozen_section(entry)
    if found is None:
        return None
    path, key = found
    parts = path.split("/")
    if "\\" in path or path.startswith("/") or any(p in ("", ".", "..") for p in parts):
        return f"tests.files {entry!r}: name the manifest by its exact path from the repository's top, such as `pyproject.toml` or `web/package.json`"
    if parts[-1] not in SECTION_MANIFESTS or any(c in path for c in "*?["):
        return f"tests.files {entry!r} names a section of {path!r}; only {' and '.join(SECTION_MANIFESTS)} have sections aidd freezes"
    if not _SECTION_KEY.match(key):
        return f"tests.files {entry!r}: name the section as a dotted key, such as `tool.pytest` or `scripts.test`"
    return None


# npm runs `pretest` and `posttest` around `test`, and a script can run any other in forms no list keeps up with
# (`npm run --silent x`, `run-s`, `concurrently "npm:x"`, `$npm_execpath`). So `package.json#scripts.test` freezes only
# those three when each is one known test runner and plain words; any other freezes every script, failing closed.
# Runners that run tests themselves (c8 and nyc wrap another command, so they are not among them).
_TEST_RUNNERS = frozenset({"vitest", "jest", "mocha", "ava", "tap", "playwright", "cypress", "node"})
# Plain words only, one space apart: any other character (a tab, a newline, `$`, `;`, `%`, `^`) fails closed.
_PLAIN = re.compile(r"[A-Za-z0-9_./:=@,+-]+(?: [A-Za-z0-9_./:=@,+-]+)*")
_RUNNER = re.compile(r"\b(?:npm|npx|yarn|pnpm|bun|bunx|deno|run-s|run-p|npm-run-all|concurrently|turbo|nx|lerna|wireit|c8|nyc)\b|--run\b")


def _self_contained(command: object) -> bool:
    """Whether a script is one known test runner in plain words, which runs no other script."""
    if not isinstance(command, str) or not _PLAIN.fullmatch(command) or _RUNNER.search(command):
        return False
    words = command.split(" ")
    return words[0] in _TEST_RUNNERS and (words[0] != "node" or words[1:2] == ["--test"])


def _test_scripts(scripts: dict) -> dict:
    """The scripts `npm test` runs: test, pretest, and posttest when each is self-contained, else every script."""
    found = {name: scripts[name] for name in ("pretest", "test", "posttest") if name in scripts}
    return found if all(_self_contained(v) for v in found.values()) else dict(scripts)


def section_value(path: str, text: str, key: str) -> object:
    """The value at dotted `key` in manifest `path`'s text, None when absent; _UNREADABLE when the text does not parse.
    `scripts.test` of a package.json is every script `npm test` runs (_test_scripts)."""
    import tomllib

    try:
        data: object = tomllib.loads(text) if SECTION_MANIFESTS.get(path.rsplit("/", 1)[-1]) == "toml" else json.loads(text)
    except (ValueError, RecursionError):
        return _UNREADABLE
    if key == "scripts.test" and SECTION_MANIFESTS.get(path.rsplit("/", 1)[-1]) == "json":
        scripts = data.get("scripts") if isinstance(data, dict) else None
        return (_test_scripts(scripts) or None) if isinstance(scripts, dict) else None
    for part in key.split("."):
        if not isinstance(data, dict):
            return None
        data = data.get(part)
    return data


def sections_changed(path: str, before: str | None, after: str | None) -> list[str]:
    """The test sections (TEST_SECTIONS) of manifest `path` that differ between two texts (None: no file); every one
    when either text does not parse, so an unreadable manifest counts as changed."""
    keys = TEST_SECTIONS.get(path.rsplit("/", 1)[-1], ())
    old = {k: section_value(path, before, k) if before is not None else None for k in keys}
    new = {k: section_value(path, after, k) if after is not None else None for k in keys}
    if _UNREADABLE in old.values() or _UNREADABLE in new.values():
        return list(keys)
    return [k for k in keys if old[k] != new[k]]


def test_sections_in(path: str, text: str) -> list[str]:
    """The test sections manifest `path` holds, as tests.files entries (`pyproject.toml#tool.pytest`)."""
    keys = TEST_SECTIONS.get(path.rsplit("/", 1)[-1], ())
    return [f"{path}#{k}" for k in keys if section_value(path, text, k) not in (None, _UNREADABLE)]


def section_digest(entry: str, tree: dict[str, str], read) -> str | None:
    """What the Spec hash holds for a frozen section: its value as canonical JSON, None when the manifest is absent. Failing
    closed: with no way to read the file, or a file that does not parse, the whole file's blob id, so any change counts."""
    path, key = frozen_section(entry) or ("", "")
    if path not in tree:
        return None
    text = read(path) if read else None
    value = section_value(path, text, key) if text is not None else _UNREADABLE
    if value is _UNREADABLE:
        return f"blob:{tree[path]}"
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
