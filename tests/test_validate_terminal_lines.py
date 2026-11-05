"""`aidd validate` prints each message as one terminal line, whatever a file's value holds."""

from __future__ import annotations

import argparse
import contextlib
import io
import unittest
from unittest import mock

from helpers import ROOT  # noqa: F401

from aidd.cli.commands import reading

# What a YAML value may hold through `"\\u001b"` and `"\\n"`: an escape that clears the screen or sets the title, a line
# break that starts a line of its own, and a mark that flips the reading direction.
HOSTILE = "PM-1\x1b[2J\x1b]0;title\x07\nerror: none, all clear\u202e"


class ValidateTerminalLinesTests(unittest.TestCase):
    def printed(self, found: list[str]) -> str:
        args = argparse.Namespace(paths=["x.md"], json=False)
        out = io.StringIO()
        with (
            mock.patch.object(reading, "_config_errors", return_value=[]),
            mock.patch("aidd.workitems.validation.validate_file", return_value=found),
            contextlib.redirect_stdout(out),
        ):
            reading.cmd_validate(args)
        return out.getvalue()

    def test_each_kind_of_message_is_one_safe_line(self):
        from aidd import workitems

        cases = {
            "an error": f"x.md: id {HOSTILE} is wrong",
            "a warning": f"{workitems.WARNING}x.md: owner {HOSTILE} was due",
            "a note": f"{workitems.NOTE}x.md: {HOSTILE}",
        }
        for name, message in cases.items():
            with self.subTest(name):
                text = self.printed([message])
                self.assertEqual(len(text.splitlines()), 2, "the message and the count line, and no line a value started")
                for bad in ("\x1b", "\x07", "\u202e"):
                    self.assertNotIn(bad, text, name)
                self.assertIn("PM-1", text)

    def test_a_plain_message_prints_as_it_is(self):
        self.assertIn("error: x.md: status must be one of draft, ready", self.printed(["x.md: status must be one of draft, ready"]))


if __name__ == "__main__":
    unittest.main()
