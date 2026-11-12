"""A test command's `related_tests` (`aidd test --changed`): the command that runs only the tests the runner relates to the change,
and when it runs instead of the full command. Only a quick check narrows, so a full run, a run that gates a merge, and a red run
never read this module's answer (`runner.run_tests`)."""

from __future__ import annotations

import json
from pathlib import Path

from aidd import config
from aidd.kernel import globs
from aidd.kernel.regular_files import link_on_the_way

# The longest command a narrowed run starts, in characters, under the 32,767 that Windows allows a command line: a longer one
# would not start at all, so it runs the full command instead.
RELATED_TESTS_MAX_CHARS = 30_000


def related_tests_command(command: dict, paths: list[str], base_sha: str, top: str) -> tuple[list[str] | None, str]:
    """What `aidd test --changed` runs for a config command with `related_tests`: its `related_tests.command`, with each changed
    path from the command's folder for `{changed_paths}` and the base commit for `{base_commit}`. It narrows only when the runner
    can trace every change the command covers (each changed path, or each one its `when_changed` matches): each matches `sees`,
    is a regular file in the working tree, lies inside the folder the command runs in, and cannot be read as an option. Else it
    gives None and why, and the full command runs. Matching `sees` keeps the case of the letters, so it never narrows more."""
    related = command.get("related_tests")
    if not related:
        return None, ""
    covered = [p for p in paths if not command.get("when_changed") or globs.match_any(command["when_changed"], p, fold_case=True)]
    folder = globs.normal_dir(command.get("runs_in") or ".")
    inside = "" if folder == "." else folder.rstrip("/") + "/"
    reasons = (
        ("matches no glob of its `related_tests.sees`", lambda p: not globs.match_any(related["sees"], p)),
        (
            "is deleted, a link, or no regular file, which the runner cannot trace",
            lambda p: bool(link_on_the_way(Path(top), p)) or not (Path(top) / p).is_file(),
        ),
        (f"lies outside {folder}, the folder it runs in", lambda p: not p.startswith(inside)),
        ("starts with `-`, so the runner could read it as an option", lambda p: p[len(inside) :].startswith("-")),
    )
    for why, refuses in reasons:
        found = [p for p in covered if refuses(p)]
        if found:
            return None, f"{found[0]}{f' and {len(found) - 1} more' if len(found) > 1 else ''} {why}"
    if not covered:
        return None, "no changed path is one it covers"
    argv: list[str] = []
    for word in related["command"]:
        argv += [p[len(inside) :] for p in covered] if word == config.CHANGED_PATHS else [word.replace(config.BASE_COMMIT, base_sha)]
    if len(" ".join(argv)) > RELATED_TESTS_MAX_CHARS:
        return None, f"its {len(covered)} changed paths make a command longer than {RELATED_TESTS_MAX_CHARS:,} characters"
    return argv, ""


def narrowed_commands(commands: list[tuple[dict, str]], paths: list[str], base_sha: str, top: str) -> tuple[dict[int, list[str]], list[str]]:
    """For `--changed`: each config command that runs only its related tests (by identity, with the command it runs), and a note
    for each command with `related_tests` that runs in full, with why. A Spec's command always runs in full. A command with no
    `related_tests` whose runner has a related-tests mode (`schemas/test-runners.json`) gets a note with the form to add."""
    narrowed: dict[int, list[str]] = {}
    notes: list[str] = []
    for c, src in commands:
        if src != "config":
            continue
        if not c.get("related_tests"):
            if suggested := config.related_tests_suggestion(c["command"]):
                notes.append(
                    f"{c['name']} ran in full. Its runner can run only the tests related to the change, so `--changed` can too: add "
                    f"`related_tests: {{command: {json.dumps(suggested)}, sees: [<the source globs it traces>]}}` to it in {config.CONFIG_PATH}"
                )
            continue
        argv, why = related_tests_command(c, paths, base_sha, top)
        if argv is None:
            notes.append(f"{c['name']} ran in full, not only its related tests: {why}")
        else:
            narrowed[id(c)] = argv
    return narrowed, notes
