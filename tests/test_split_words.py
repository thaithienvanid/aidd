"""aidd splits a command line into words in time linear in its length, and gives the words `shlex` gives.

`shlex` joins a word one character at a time, so one long word costs time squared: a 2 MB `run:` line stalled the delegate
check for minutes. `processes.split_words` is the one splitter, and `shlex` is its oracle: the differential tests below
compare the two on every short string over a small alphabet and on tens of thousands of random ones. The timing tests
run each caller on a line where `shlex` takes seconds, so a caller that goes back to it fails in seconds and never hangs."""

import itertools
import random
import shlex
import tempfile
import sys
import time
import unittest
from unittest import mock
from pathlib import Path

import helpers  # noqa: F401  (puts src on sys.path)

from aidd import risk
from aidd.delegation import commands as delegated
from aidd.delegation import diff_signals
from aidd.kernel import processes
from aidd.risk import commands, shell
from aidd.setup import mcp_wiring

# Quotes, backslashes, every shlex whitespace, characters shlex treats as comments or expansions, the punctuation that
# splits a word in `punctuation` mode, a character only str.split() calls whitespace, and non-ASCII text.
ALPHABET = ["'", '"', "\\", " ", "\t", "\n", "\r", "#", "$", "a", "b", "é", "日", ";", "&", "|", "(", ")", "<", ">", "=", "-", "\x0b", "\xa0", "\x00"]
SMALL = ["'", '"', "\\", " ", "\n", "a", ";"]
LONG = 400_000  # a word on which shlex takes seconds, and split_words takes milliseconds
FAST = 1.0  # seconds: the most a caller may take on it


def oracle(line: str, punctuation: bool) -> tuple[str, list[str] | str]:
    """What shlex gives for `line`: the words, or its error."""
    try:
        if punctuation:
            lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
            lexer.whitespace_split = True
            lexer.commenters = ""
            return "words", list(lexer)
        return "words", shlex.split(line)
    except ValueError as exc:
        return "error", str(exc)


def ours(line: str, punctuation: bool) -> tuple[str, list[str] | str]:
    try:
        return "words", processes.split_words(line, punctuation=punctuation)
    except ValueError as exc:
        return "error", str(exc)


def seconds(call, *args) -> float:
    """The processor time `call` takes, which a busy machine (the suite runs ten files at a time) does not stretch."""
    start = time.process_time()
    call(*args)
    return time.process_time() - start


class SameWordsAsShlexTests(unittest.TestCase):
    def check(self, line: str):
        for punctuation in (False, True):
            self.assertEqual(ours(line, punctuation), oracle(line, punctuation), (line, punctuation))

    def test_the_cases_that_differ_by_one_rule(self):
        for line in (
            "",
            "   ",
            "a b",
            "a  \t b\nc\rd",
            "''",
            '""',
            "a''b",
            "'a b' \"c d\"",
            "a\\ b",
            "a\\\nb",
            '"a\\"b"',
            '"a\\\\b"',
            '"a\\nb"',
            "'a\\nb'",
            "# not a comment",
            "a#b $x `y` $(z)",
            "a;b&&c||d|e",
            "a ; b",
            ";;a;;",
            "'a';b",
            "(a)",
            "a\x0bb \xa0c",
            "é 日本",
            "'",
            '"',
            "\\",
            "a'b",
            'a"b',
            "a\\",
            '"a\\',
            "'a\\",
            '"a\\"',
            "a '' ",
            "x\\\\\\",
        ):
            with self.subTest(line=line):
                self.check(line)

    def test_every_short_line_over_a_small_alphabet(self):
        for length in range(7):
            for chars in itertools.product(SMALL, repeat=length):
                self.check("".join(chars))

    def test_random_lines(self):
        rng = random.Random(20261110)
        for _ in range(60_000):
            self.check("".join(rng.choice(ALPHABET) for _ in range(rng.choice((1, 2, 3, 5, 8, 13, 21, 40)))))

    def test_the_same_error_for_a_quote_or_a_backslash_left_open(self):
        for line, message in (
            ("'a", "No closing quotation"),
            ('"a', "No closing quotation"),
            ("a\\", "No escaped character"),
            ('"a\\', "No escaped character"),
        ):
            with self.assertRaisesRegex(ValueError, message):
                processes.split_words(line)

    def test_a_python_with_unsafe_possessive_repeats_keeps_shlex(self):
        """CPython before 3.11.5 can lose its place after a failed possessive group repeat (gh-106052)."""
        self.assertEqual(processes.POSSESSIVE_REPEATS_WORK, sys.version_info >= (3, 11, 5))
        with mock.patch.object(processes, "POSSESSIVE_REPEATS_WORK", False), mock.patch.object(processes, "_WORDS", {}):
            for line in ("a 'b c' \\d", 'x"y', "a;b|c", "'open"):
                for punctuation in (False, True):
                    with self.subTest(line=line, punctuation=punctuation):
                        self.assertEqual(ours(line, punctuation), oracle(line, punctuation))

    def test_split_command_uses_it_off_windows_and_keeps_its_windows_reading(self):
        self.assertEqual(processes.split_command(r"a\ b 'c d'", windows=False), ["a b", "c d"])
        self.assertEqual(processes.split_command(r"C:\x\y.exe 'c d'", windows=True), [r"C:\x\y.exe", "c d"])


class LinearTimeTests(unittest.TestCase):
    def test_one_long_word(self):
        for line in ("x" * LONG, "'" + "x" * LONG + "'", '"' + "x\\\\" * (LONG // 3) + '"', "\\a" * (LONG // 2), "'" + "x" * LONG):
            for punctuation in (False, True):
                with self.subTest(shape=line[:3], punctuation=punctuation):
                    self.assertLess(seconds(ours, line, punctuation), FAST)

    def test_many_words_and_many_pieces(self):
        for line in ("a " * LONG, "'a'" * LONG, "a;" * LONG):
            with self.subTest(shape=line[:3]):
                self.assertLess(seconds(ours, line, True), FAST * 3)


class EachCallerIsLinearTests(unittest.TestCase):
    """Each fails in seconds when its caller goes back to `shlex.split` or to a list it empties from the front."""

    def test_the_command_pattern_reader(self):
        self.assertLess(seconds(lambda: commands.normalize("echo " + "x" * LONG)), FAST)

    def test_the_other_repository_reader(self):
        self.assertLess(seconds(lambda: commands.names_another_repository("git " + "x" * LONG)), FAST)

    def test_the_folder_reader(self):
        self.assertLess(seconds(lambda: commands.folder_after("cd " + "x" * LONG, "/")), FAST)

    def test_a_whole_command_level(self):
        rules = risk.rule_set(None)
        self.assertLess(seconds(lambda: risk.command_level(rules, "echo " + "x" * LONG, cwd=None)), FAST)

    def test_the_delegated_command_reader(self):
        self.assertLess(seconds(lambda: delegated.words("git push origin " + "x" * LONG)), FAST)

    def test_the_launcher_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            launcher = Path(tmp) / "aidd"
            launcher.write_text("#!/bin/sh\nexec " + "x" * LONG + ' "$@"\n', encoding="utf-8")
            self.assertLess(seconds(lambda: mcp_wiring.launcher_problem(launcher)), FAST)

    def test_the_operator_command_splitter(self):
        self.assertLess(seconds(lambda: processes.split_command("x" * LONG, windows=False)), FAST)

    def test_a_line_of_many_settings_or_redirections(self):
        """A list emptied from the front costs time squared in its length: 250,000 words took seconds."""
        words = 250_000
        self.assertLess(seconds(lambda: shell.tokens("A=1 " * words + "x")), FAST)
        self.assertLess(seconds(lambda: shell.without_redirections("echo " + "x " * words)), FAST)

    def test_a_reader_with_many_options(self):
        """`grep` re-read its rest of the line at every option: 20,000 options took seconds."""
        rules = risk.rule_set(None)
        self.assertLess(seconds(lambda: commands.file_read_actions(rules, "grep " + "-i " * 20_000 + "x f")), FAST)

    def test_the_escaped_key_reader(self):
        """A quoted key's two runs around a backslash backed up over every backslash: 48,000 characters took 4 s."""
        self.assertLess(seconds(lambda: diff_signals.ESCAPED_KEY.search("run: 'a" + "\\a" * 24_000)), FAST)
        for line, escaped in (('  "envi\\x72onment": prod', True), ("{'a\\b': 1}", True), ('  "environment": prod', False), ("run: 'a\\b'", False)):
            with self.subTest(line):
                self.assertEqual(bool(diff_signals.ESCAPED_KEY.search(line)), escaped)

    def test_a_folder_name_too_long_for_the_file_system_reads_as_unknown(self):
        self.assertIsNone(commands.folder_after("cd " + "x" * 300, "/"))


class TheAnswerIsUnchangedTests(unittest.TestCase):
    def test_long_and_short_commands_keep_their_levels(self):
        rules = risk.rule_set(None)
        for line, level in (
            ("git push --force origin main", "ask"),
            ("rm -rf build", "ask"),
            ("echo " + "x" * 50_000, "allow"),
            ("cat " + "a " * 5_000 + ".env", "ask"),
            ("grep -e x " + "-i " * 5_000 + ".env", "ask"),
            ("sudo " + "-n " * 5_000 + "git push --force origin main", "ask"),
            ("A=1 " * 5_000 + "git push --force origin main", "ask"),
            ("echo " + "x " * 5_000 + "&& git push -f origin main", "ask"),
        ):
            with self.subTest(line=line[:40]):
                self.assertEqual(risk.command_level(rules, line, cwd=None)["level"], level)


if __name__ == "__main__":
    unittest.main()
