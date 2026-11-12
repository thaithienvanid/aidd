"""A command aidd's own text tells an agent to run never asks by surprise. The skill, the roles, and the flows name shell
commands in backticks; each is read by the risk rules as an agent on its own branch would run it. One that asks stalls an
unattended run and breaks "ask once", unless the text means it to ask: those are listed here, each with its reason.

The invariant: for every command the shipped agent text names, the level is `allow` or `report`, or the command is in
EXPECTED_ASKS. Both directions: a listed command that stops asking fails too, so the list never holds a stale row.

And a text that names an `ask` command says in the same step, its paragraph, list item, or table row, that it asks or is
never to run (ASKS_FIRST), so no role reaches an ask as a routine step. A step that does not is a finding: fixed where the
skill or a flow says it, and listed in UNMARKED, with where it was reported, where another owner's text says it."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import helpers  # noqa: F401  # the hermetic environment
from aidd import risk

ROOT = Path(__file__).resolve().parent.parent
RS = risk.rule_set(None)
PAGES = sorted(
    [
        ROOT / "templates" / "AGENTS.snippet.md",  # the block every repository's AGENTS.md carries
        *ROOT.glob(".agents/skills/aidd/**/*.md"),
        *ROOT.glob("plugins/aidd-team/agents/*.md"),
        *ROOT.glob("plugins/aidd-team/commands/*.md"),
        *ROOT.glob("plugins/aidd-team/skills/**/*.md"),
        *ROOT.glob("plugins/aidd-packs/skills/**/*.md"),
    ]
)
PROGRAMS = ("aidd ", "git ", "gh ", "glab ", "rm ", "npm ", "cargo ", "kubectl ", "docker ", "terraform ", "aws ", "curl ")

# A command the text names because it asks, or names as one never to run: the reason is the text's own.
EXPECTED_ASKS = {
    "aidd approve <IDs>": "Intent approval is a person's gate; the text says to ask first",
    "aidd approve": "named as a person's own command, or one an agent never runs; `aidd approve*` asks at any spelling",
    "aidd approve <id>": "a person runs it in their own terminal: the Intent's `approval` field and the step that waits for them name it",
    "aidd records push": "sending the records to a remote is `records.push`, which the text says asks",
    "git merge --no-ff -m <message> <sha>": "the delegated merge, run only after the delegate's accept",
    "npm publish --dry-run": "a publish preview runs the package's own scripts, so it keeps the ask",
    "cargo publish --dry-run": "a publish preview runs a build, so it keeps the ask",
    "rm -rf": "named only as the command never to run on scratch files",
}


# How a step says that its command asks, or is never to run: "an `ask`", "asks first", "Never run".
ASKS_FIRST = re.compile(r"\bask(s|ed)?\b|\bnever\b", re.IGNORECASE)
# A step of an `ask` command that does not say so, in text another owner keeps: the finding, and where it was reported.
UNMARKED: dict[tuple[str, str], str] = {}
# Where a step starts: a list item, a table row, or a heading.
_STEP_START = re.compile(r"^\s*(?:[-*]|\d+\.|\||#)")


def step(text: str, at: int) -> str:
    """The step that holds offset `at`: its table row or heading line, or its paragraph or list item with the lines that
    continue it."""
    lines = text.split("\n")
    row = text.count("\n", 0, at)
    if lines[row].lstrip().startswith(("|", "#")):
        return lines[row]
    first = row
    while first > 0 and lines[first - 1].strip() and not _STEP_START.match(lines[first]):
        first -= 1
    last = row
    while last + 1 < len(lines) and lines[last + 1].strip() and not _STEP_START.match(lines[last + 1]):
        last += 1
    return "\n".join(lines[first : last + 1])


def instructed_steps() -> dict[str, list[tuple[str, str]]]:
    """Each command the pages name, with each page and the step that names it."""
    found: dict[str, list[tuple[str, str]]] = {}
    for page in PAGES:
        text = page.read_text(encoding="utf-8")
        for match in re.finditer(r"`([^`\n]{3,200})`", text):
            command = match.group(1).strip()
            if command.startswith(PROGRAMS):
                found.setdefault(command, []).append((page.relative_to(ROOT).as_posix(), step(text, match.start())))
    return found


def instructed() -> dict[str, set[str]]:
    return {command: {page for page, _ in steps} for command, steps in instructed_steps().items()}


def level(command: str) -> str:
    return risk.command_level(RS, command, branch="feat")["level"]


class InstructedCommandsTests(unittest.TestCase):
    def test_the_pages_name_commands(self):
        self.assertGreater(len(instructed()), 100, "the scan found too few commands to mean anything")

    def test_no_instructed_command_asks_by_surprise(self):
        for command, pages in sorted(instructed().items()):
            if command in EXPECTED_ASKS:
                continue
            with self.subTest(command=command, pages=sorted(pages)[:2]):
                self.assertNotEqual(level(command), "ask", "the text tells an agent to run this, and it asks: fix the rule or the text, or list the reason")

    def test_every_listed_ask_is_named_and_still_asks(self):
        named = instructed()
        for command in EXPECTED_ASKS:
            with self.subTest(command=command):
                self.assertIn(command, named, "the text no longer names this command: drop the row")
                self.assertEqual(level(command), "ask", "this command no longer asks: drop the row")

    def test_every_step_that_names_an_ask_command_says_it_asks(self):
        """Table-driven over every instructed command: each one at `ask`, on each page and step that names it."""
        at_ask = {c: steps for c, steps in instructed_steps().items() if level(c) == "ask"}
        self.assertEqual(sorted(at_ask), sorted(EXPECTED_ASKS), "the commands found at `ask` are the listed ones")
        for command, steps in sorted(at_ask.items()):
            for page, text in steps:
                with self.subTest(command=command, page=page):
                    if (command, page) in UNMARKED:
                        self.assertIsNone(ASKS_FIRST.search(text), "this step says it asks now: drop its UNMARKED row")
                    else:
                        self.assertRegex(text, ASKS_FIRST, "the step tells an agent to run an `ask` command and does not say it asks first")
        for command, page in UNMARKED:
            with self.subTest(unmarked=command):
                self.assertIn(page, {p for p, _ in at_ask.get(command, [])}, "the text no longer names it there: drop the row")

    def test_a_step_is_its_paragraph_list_item_or_row(self):
        text = "Intro line\ncontinues `git a`.\n\n- item `git b`\n  more\n- next\n| row `git c` | x |\n## Head `git d`\n"
        cases = [
            ("git a", "Intro line\ncontinues `git a`."),
            ("git b", "- item `git b`\n  more"),
            ("git c", "| row `git c` | x |"),
            ("git d", "## Head `git d`"),
        ]
        for command, want in cases:
            with self.subTest(command=command):
                self.assertEqual(step(text, text.index(command)), want)

    def test_recording_an_answered_ask_never_asks_again(self):
        """The skill tells the agent to record an answered ask. A record whose data names a push is no push of the records."""
        for action in ("git.push", "git.push.force", "records.push", "pr.merge"):
            line = f'aidd records add --type decision --by claude-code/a-model --subject SPEC-4 --data \'{{"action": "{action}"}}\''
            with self.subTest(action=action):
                self.assertNotEqual(level(line), "ask")
        spellings = ("aidd records  push", 'aidd records "push"', "aidd records 'push'", "aidd  records   push --remote origin")
        for line in (
            "aidd records push",
            "cd x && aidd records push --remote origin",
            "python3 -m aidd records push",
            "git push origin refs/aidd/records",
            *spellings,
        ):
            with self.subTest(line=line):
                self.assertEqual(level(line), "ask")


if __name__ == "__main__":
    unittest.main()
