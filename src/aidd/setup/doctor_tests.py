"""`aidd doctor` on the config's test commands: a note for each one whose runner can run only the tests related to a change, so
`aidd test --changed` can too, with the `related_tests` form to add. It is advice a person adapts, never a value aidd writes."""

from __future__ import annotations

import json

from aidd import config


def related_tests_lines(cfg: config.Config) -> list[tuple[str, str]]:
    """One `info` line for each `tests` entry with no `related_tests` whose runner's documentation gives a related-tests mode
    (`config.related_tests_suggestion`), and none for an entry that has one or whose runner has none. The name and the command
    print escaped, so a value from the config cannot start a line of its own."""
    out: list[tuple[str, str]] = []
    for test in cfg.tests or []:
        if not isinstance(test, dict) or test.get("related_tests"):
            continue
        if suggested := config.related_tests_suggestion(test.get("command")):
            out.append(
                (
                    "info",
                    f"tests {json.dumps(str(test.get('name')))}: its runner can run only the tests related to a change, so `aidd test --changed` "
                    f"can too: add `related_tests: {{command: {json.dumps(suggested)}, sees: [<the source globs it traces>]}}` to it in "
                    f"{config.CONFIG_PATH}. A full `aidd test` still runs the whole command",
                )
            )
    return out
