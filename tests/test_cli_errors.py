"""A wrong or missing argument is answered in a line or two that say what to type (clig.dev), never a usage dump."""

import contextlib
import io
import unittest

from helpers import ROOT  # noqa: F401

from aidd.cli import app


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
        self.assertIn("'next' is not an aidd command. `aidd --help` lists them.", err)
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

    def test_aidd_alone_prints_the_overview(self):
        code, err = run()
        self.assertEqual(code, 2)
        self.assertIn("Setup:", err)
        self.assertIn("Decide:", err)


if __name__ == "__main__":
    unittest.main()
