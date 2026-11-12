"""A wrong or missing argument is answered in a line or two that say what to type (clig.dev), never a usage dump."""

import argparse
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
        code, err = run("staus")
        self.assertEqual(code, 2)
        self.assertEqual(err, "aidd: 'staus' is not an aidd command. Did you mean `aidd status`?\n`aidd --help` shows every option.\n")

    def test_an_unknown_command_with_nothing_close_is_not_guessed(self):
        code, err = run("frobnicate")
        self.assertEqual(code, 2)
        self.assertEqual(err, "aidd: 'frobnicate' is not an aidd command. `aidd help --all` lists them.\n")
        self.assertNotIn("Did you mean", err)

    def test_a_missing_argument_says_what_in_words_and_gives_an_example(self):
        code, err = run("new")
        self.assertEqual(code, 2)
        self.assertIn("aidd new: missing what to create", err)
        self.assertIn('For example: aidd new spec "Add a percentage discount"', err)
        self.assertLessEqual(len(err.splitlines()), 3)  # never the full usage

    def test_a_wrong_choice_and_an_unknown_option_name_the_command(self):
        self.assertIn("aidd new: 'specc' is not a choice. Did you mean `spec`?", run("new", "specc")[1])
        self.assertIn("aidd risk: unknown option --pths. Did you mean `--paths`?", run("risk", "--pths")[1])

    def crash(self, env: dict[str, str], error: BaseException | None = None) -> tuple[int, str]:
        """`aidd doctor` with its command replaced by one that hits a bug, or raises `error`."""
        import os
        from unittest import mock

        def boom(_args):
            raise error or ZeroDivisionError("division by zero")

        real = parser.build_parser

        def build(**kw):
            p = real(**kw)
            p._subparsers._group_actions[0].choices["doctor"].set_defaults(func=boom)
            return p

        with mock.patch.object(parser, "build_parser", build), mock.patch.dict(os.environ, env):
            return run("doctor")

    def test_a_crash_says_it_is_a_bug_and_where_to_report_it(self):
        code, err = self.crash({"AIDD_DEBUG": "0"})
        self.assertEqual(code, 2)
        self.assertIn("aidd: internal error: ZeroDivisionError: division by zero\n", err)
        self.assertIn("this is a bug in aidd: run the command again with AIDD_DEBUG=1 for the traceback", err)
        self.assertIn(f"report it at {app.BUG_REPORT_URL} with the output of `aidd --version` and `aidd doctor --json`", err)
        self.assertIn("The report is public, so first remove anything private from that output, such as emails, tokens, and paths", err)
        self.assertNotIn("Traceback", err)

    def test_ctrl_c_stops_in_one_line_and_checks_for_no_update(self):
        from unittest import mock

        from aidd.setup import self_updating

        with mock.patch.object(self_updating, "auto_update") as update:
            code, err = self.crash({"AIDD_DEBUG": "0"}, KeyboardInterrupt())
            self.assertEqual((code, err), (130, "aidd: stopped\n"))
            update.assert_not_called()  # the daily check could reach the network, or fail on a second Ctrl-C
            self.crash({"AIDD_DEBUG": "0"})
            update.assert_called_once()  # the control: any other end runs it

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
            return arguments.config_or_none_quiet(argparse.Namespace()), err.getvalue()

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
            args = argparse.Namespace()
            self.assertIsNone(arguments.config_or_none_quiet(args))
            self.assertIsNone(arguments.config_or_none_quiet(args))
        self.assertEqual(len(err.getvalue().splitlines()), 1, err.getvalue())

    def test_no_config_is_quiet(self):
        self.assertEqual(self.quiet(None), (None, ""))


class OutsideARepository(unittest.TestCase):
    """In a folder that no git repository holds, a command that works on files alone runs, and one that works on a
    repository stops with the next step in words, never git's own `fatal: not a git repository`."""

    NEW_DESIGN = ("prototype", "--new-design", "index.html", "--title", "A direction")
    # (the commands run in turn, in one fresh folder; whether the last needs a repository)
    CASES = [
        ((NEW_DESIGN,), False),
        ((NEW_DESIGN, ("prototype", "--check", "index.html")), False),
        ((NEW_DESIGN, ("prototype", "--components", "index.html")), False),
        ((("new", "design-system"),), False),
        ((("new", "spec", "SPEC-1", "--title", "A spec"),), False),
        ((("standard", "--stacks"),), False),
        ((("risk", "--action", "pr.merge"),), False),
        ((("status",),), True),
        ((("records",),), True),
        ((("recall", "word"),), True),
        ((("status", "src"),), True),
        ((("test",),), True),
        ((("validate",),), True),
        ((("standard", "add", "python/ruff-lint-format"),), True),
    ]

    def test_each_command_works_or_names_the_next_step(self):
        from aidd.kernel import git

        for steps, needs in self.CASES:
            with self.subTest(command=" ".join(steps[-1])), tempfile.TemporaryDirectory() as d, contextlib.chdir(d):
                self.assertIsNone(git.repository_top(d), "the test folder must be in no repository")
                for argv in steps:
                    code, err = run(*argv)
                self.assertNotIn("fatal:", err)
                if needs:
                    self.assertEqual((code, err.strip()), (2, f"aidd: {git.no_repository_problem(steps[-1][0])}"))
                else:
                    self.assertEqual(code, 0, err)

    def test_git_answers_in_english_where_aidd_reads_its_words(self):
        """aidd tells "no repository" from any other failure by git's English words, so that call runs with LC_ALL=C,
        whatever language the person's git speaks."""
        from unittest import mock

        from aidd.kernel import git

        seen = []
        real = git._git
        with tempfile.TemporaryDirectory() as d, mock.patch.object(git, "_git", lambda *a: seen.append(git._environment(a[2])) or real(*a)):
            self.assertIsNone(git.repository_top(d))
        self.assertEqual([env.get("LC_ALL") for env in seen], ["C"])


if __name__ == "__main__":
    unittest.main()
