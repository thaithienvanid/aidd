"""A wrong or missing argument is answered in a line or two that say what to type (clig.dev), never a usage dump."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT  # noqa: F401

from aidd.cli import app, arguments, parser


def run(*argv: str) -> tuple[int, str]:
    err = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
        try:
            code = app.main(list(argv))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    return code, err.getvalue()


class CliErrorTests(unittest.TestCase):
    def test_a_typo_in_a_command_gets_the_close_one(self):
        code, err = run("aprove")
        self.assertEqual(code, 2)
        self.assertEqual(err, "aidd: 'aprove' is not an aidd command. Did you mean `aidd approve`?\n`aidd --help` shows every option.\n")

    def test_an_unknown_command_with_nothing_close_is_not_guessed(self):
        code, err = run("next")
        self.assertEqual(code, 2)
        self.assertEqual(err, "aidd: 'next' is not an aidd command. `aidd help --all` lists them.\n")
        self.assertNotIn("Did you mean", err)

    def test_a_missing_argument_says_what_in_words_and_gives_an_example(self):
        code, err = run("new")
        self.assertEqual(code, 2)
        self.assertIn("aidd new: missing what to create", err)
        self.assertIn('For example: aidd new spec "Add a percentage discount"', err)
        self.assertLessEqual(len(err.splitlines()), 3)  # never the full usage

    def test_a_wrong_choice_and_an_unknown_option_name_the_command(self):
        self.assertIn("aidd new: 'specc' is not one of its choices. Did you mean `spec`?", run("new", "specc")[1])
        self.assertIn("aidd list: unknown option --brnch. Did you mean `--branch`?", run("list", "--brnch")[1])

    def crash(self, env: dict[str, str]) -> tuple[int, str]:
        """`aidd doctor` with its command replaced by one that hits a bug."""
        import os
        from unittest import mock

        def boom(_args):
            raise ZeroDivisionError("division by zero")

        real = parser.build_parser

        def build(**kw):
            p = real(**kw)
            p._subparsers._group_actions[0].choices["doctor"].set_defaults(func=boom)
            return p

        with mock.patch.object(parser, "build_parser", build), mock.patch.dict(os.environ, env):
            return run("doctor")

    def test_a_crash_says_it_is_a_bug_and_where_to_report_it(self):
        from aidd.gate import rulebook

        code, err = self.crash({"AIDD_DEBUG": "0"})
        self.assertEqual(code, 2)
        self.assertIn("aidd: internal error: ZeroDivisionError: division by zero\n", err)
        self.assertIn("this is a bug in aidd: run the command again with AIDD_DEBUG=1 for the traceback", err)
        self.assertIn(f"report it at {rulebook.BUG_REPORT_URL} with the output of `aidd --version` and `aidd doctor --json`", err)
        self.assertIn("The report is public, so first remove anything private from that output, such as emails, tokens, and paths", err)
        self.assertNotIn("Traceback", err)

    def test_aidd_debug_prints_the_traceback(self):
        code, err = self.crash({"AIDD_DEBUG": "1"})
        self.assertEqual(code, 2)
        self.assertIn("Traceback (most recent call last):", err)
        self.assertIn("ZeroDivisionError: division by zero", err)
        self.assertIn("add the traceback above", err)
        self.assertNotIn("run the command again", err)

    def test_aidd_alone_prints_the_overview(self):
        code, err = run()
        self.assertEqual(code, 2)
        self.assertIn("Everyday commands:", err)
        self.assertIn("`aidd help --all`", err)


class QuietConfigTests(unittest.TestCase):
    """A command that goes on without the config says so in one line when the config exists and does not load."""

    def quiet(self, config_text: str | None) -> tuple[object, str]:
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as d, contextlib.chdir(d), contextlib.redirect_stderr(err):
            if config_text is not None:
                Path(".aidd").mkdir()
                Path(".aidd/config.yaml").write_text(config_text, encoding="utf-8")
            return arguments.config_or_none_quiet(), err.getvalue()

    def test_a_config_that_does_not_load_gets_one_line_and_the_next_step(self):
        cfg, err = self.quiet("profile: [unclosed\n")
        self.assertIsNone(cfg)
        self.assertEqual(len(err.splitlines()), 1, err)
        self.assertIn(".aidd/config.yaml does not load", err)
        self.assertIn("`aidd validate`", err)

    def test_a_command_that_reads_it_twice_says_it_once(self):
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as d, contextlib.chdir(d), contextlib.redirect_stderr(err):
            Path(".aidd").mkdir()
            Path(".aidd/config.yaml").write_text("profile: [unclosed\n", encoding="utf-8")
            self.assertIsNone(arguments.config_or_none_quiet())
            self.assertIsNone(arguments.config_or_none_quiet())
        self.assertEqual(len(err.getvalue().splitlines()), 1, err.getvalue())

    def test_the_reason_reaches_the_terminal_with_no_control_character(self):
        line = arguments.config_load_problem(ValueError("bad \x1b[2J\x07value‮ here"))
        for c in ("\x1b", "\x07", "‮"):
            self.assertNotIn(c, line)
        self.assertIn("bad  [2J value  here", line)

    def test_no_config_is_quiet(self):
        self.assertEqual(self.quiet(None), (None, ""))

    def test_a_long_reason_is_cut_to_a_few_words(self):
        line = arguments.config_load_problem(ValueError("x" * 500 + "\nsecond line"))
        self.assertLess(len(line), 260)
        self.assertNotIn("second line", line)


if __name__ == "__main__":
    unittest.main()
