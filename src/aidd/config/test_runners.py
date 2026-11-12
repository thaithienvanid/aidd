"""What aidd knows about a test runner (`schemas/test-runners.json`): its name, and the exits its own documentation gives for a run in
which no test failed. One row for each runner, so another runner is a row and no code. Each fact is read when first asked,
never on import. These exits decide whether a red run proves new behavior, so a row needs the runner's documentation as its source."""

from __future__ import annotations

import functools
import re

from aidd.kernel import resources


@functools.cache
def test_runner_names() -> tuple[str, ...]:
    """The runners aidd knows by name, in the table's order."""
    return tuple(resources.load_json("test-runners.json")["runners"])


@functools.cache
def _not_red() -> tuple[tuple[frozenset[str], frozenset[int]], ...]:
    """For each runner row that gives exits, the words that show a command runs it and the exits it gives."""
    rows = resources.load_json("test-runners.json")["runners"].values()
    return tuple((frozenset(row["command_words"]), frozenset(e["exit"] for e in row["not_red_exits"])) for row in rows if row.get("not_red_exits"))


# The words a test command's `related_tests.command` may hold in braces: the changed paths, as arguments of their own, and the
# commit the branch left the base at. `aidd test --changed` puts in their values (`testing.runner.related_tests_command`).
CHANGED_PATHS = "{changed_paths}"
BASE_COMMIT = "{base_commit}"
_BRACED = re.compile(r"\{[^{}]*\}")


def related_tests_problems(raw: object) -> list[tuple[str, str]]:
    """Each `tests[].related_tests.command` that cannot narrow honestly, as (JSON path, message): one with neither placeholder
    would run what its runner finds by itself, such as nothing after a commit; `{changed_paths}` inside a longer argument
    cannot become several paths; and any other word in braces is a typo aidd cannot tell from a placeholder."""
    tests = raw.get("tests") if isinstance(raw, dict) else None
    out: list[tuple[str, str]] = []
    for i, test in enumerate(tests if isinstance(tests, list) else []):
        command = ((test.get("related_tests") if isinstance(test, dict) else None) or {}).get("command")
        if not isinstance(command, list):
            continue
        where, words = f"$.tests[{i}].related_tests.command", [w for w in command if isinstance(w, str)]
        unknown = sorted({b for w in words for b in _BRACED.findall(w)} - {CHANGED_PATHS, BASE_COMMIT})
        if unknown:
            out.append((where, f"{', '.join(unknown)} is no placeholder aidd knows: use {CHANGED_PATHS} or {BASE_COMMIT}"))
        elif any(CHANGED_PATHS in w and w != CHANGED_PATHS for w in words):
            out.append((where, f"{CHANGED_PATHS} must be an argument of its own, since it becomes one argument for each changed path"))
        elif not any(CHANGED_PATHS in w or BASE_COMMIT in w for w in words):
            out.append(
                (where, f"it holds neither {CHANGED_PATHS} nor {BASE_COMMIT}, so it would not run the tests of this change: add the one its runner takes")
            )
    return out


@functools.cache
def _related_rows() -> tuple[tuple[frozenset[str], tuple[str, ...]], ...]:
    """For each runner row whose documentation gives a related-tests mode, the words that show a command runs it and the
    arguments that follow the runner's word in that mode."""
    rows = resources.load_json("test-runners.json")["runners"].values()
    return tuple(
        (frozenset(row["command_words"]), tuple(row["related_tests"]["arguments"])) for row in rows if (row.get("related_tests") or {}).get("arguments")
    )


def related_tests_suggestion(command: object) -> list[str] | None:
    """A `related_tests.command` to suggest for a test command, from the runner table: the command up to the runner's word, then
    the arguments of the runner's own related-tests mode. None when the command names no runner whose documentation gives one,
    such as `npm test`. A suggestion is advice a person adapts and writes, never a value aidd writes: it drops the options the
    command had after the runner's word, and the person decides `sees`."""
    if not isinstance(command, list):
        return None
    words = [re.split(r"[\\/]", str(w))[-1].lower().removesuffix(".exe") for w in command]
    for named, arguments in _related_rows():
        at = next((i for i, w in enumerate(words) if w in named), None)
        if at is not None:
            return [str(w) for w in command[: at + 1]] + list(arguments)
    return None


def no_test_failed_exit(command: object, code: int) -> bool:
    """Whether a runner the command names gives `code` for a run in which no test failed. A command names a runner when a word of
    it has, as its last path part in lower case and without `.exe`, one of the row's `command_words`, in any wrapper (`uv run`,
    `python -m`). A code no row gives, and a command that names no runner, give False, so the exit stays a real failure."""
    if not isinstance(command, list):
        return False
    words = {re.split(r"[\\/]", str(w))[-1].lower().removesuffix(".exe") for w in command}
    return any(code in exits and not words.isdisjoint(named) for named, exits in _not_red())
