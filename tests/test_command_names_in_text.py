"""Every `aidd <word>` that a message or a comment in the source puts in backticks is a command that exists, so a next step
never names one aidd lacks (`aidd owners` and `aidd observe` once did). The commands come from the parser itself."""

import argparse
import re
import unittest

from helpers import ROOT

from aidd.cli import parser as cli_parser

MENTION = re.compile(r"`aidd ([a-z][a-z-]*)")


def commands() -> set[str]:
    top = cli_parser.build_parser()
    return {name for action in top._actions if isinstance(action, argparse._SubParsersAction) for name in action.choices}


class CommandNamesInText(unittest.TestCase):
    def test_every_backticked_aidd_word_in_src_is_a_command(self):
        known = commands()
        self.assertIn("status", known)
        for path in sorted((ROOT / "src").rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for found in MENTION.finditer(text):
                line = text[: found.start()].count("\n") + 1
                with self.subTest(file=path.relative_to(ROOT).as_posix(), line=line):
                    self.assertIn(found.group(1), known, f"`aidd {found.group(1)}` is no command")

    def test_the_check_sees_a_word_that_is_no_command(self):
        self.assertEqual(MENTION.findall("run `aidd owners` or `aidd status`"), ["owners", "status"])
        self.assertNotIn("owners", commands())


if __name__ == "__main__":
    unittest.main()
