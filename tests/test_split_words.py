"""aidd splits a command line into words in time linear in its length, and gives the words `shlex` gives.

`shlex` joins a word one character at a time, so one long word costs time squared: a 2 MB `run:` line stalled the delegate
check for minutes. `processes.split_words` is the one splitter, and `shlex` is its oracle: the differential tests below
compare the two on every short string over a small alphabet and on tens of thousands of random ones. The cost tests never
time anything, because a time depends on the machine and fails a slow one that has no defect. They count the work each caller
does at three sizes of one input, so work that grows faster than the input fails on any machine: the characters a caller
hands to the splitter, the characters the splitter hands to its own patterns or has them scan, the words it takes from a queue,
and the words it checks as settings. The cost the engine hides, in a pattern, is held by the pattern's shape: no repeat that
can give back what it took."""

import ast
import contextlib
import io
import itertools
import random
import re
import shlex
import tempfile
import sys
import unittest
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from unittest import mock
from pathlib import Path

import helpers  # noqa: F401  (puts src on sys.path)

from aidd import risk
from aidd.delegation import commands as delegated
from aidd.delegation import diff_signals
from aidd.kernel import processes
from aidd.risk import commands, file_reads, file_writes, shell
from aidd.setup import mcp_wiring

# Quotes, backslashes, every shlex whitespace, characters shlex treats as comments or expansions, the punctuation that
# splits a word in `punctuation` mode, a character only str.split() calls whitespace, and non-ASCII text.
ALPHABET = ["'", '"', "\\", " ", "\t", "\n", "\r", "#", "$", "a", "b", "é", "日", ";", "&", "|", "(", ")", "<", ">", "=", "-", "\x0b", "\xa0", "\x00"]
SMALL = ["'", '"', "\\", " ", "\n", "a", ";"]
LONG = 400_000  # a word on which shlex takes seconds, and split_words takes milliseconds
GROWTH = 4  # the factor between the sizes a cost test runs; work that grows by more than this factor is not linear
MANY = 25_600  # words or pieces, a multiple of GROWTH squared so that each size is exactly GROWTH times the one before


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


@dataclass
class Work:
    """What one call did: the characters it handed to the splitter and how many times, the characters the splitter's own patterns
    were handed or scanned and how many times they were called, the words it took from a queue, and the words it checked as a
    setting. `line` is the text the splitter is working on, which is no field of the count."""

    chars: int = 0
    splits: int = 0
    pattern_chars: int = 0
    pattern_calls: int = 0
    pops: int = 0
    setting_checks: int = 0
    line: str | None = field(default=None, repr=False, compare=False)


class CountedSetting:
    """The pattern for `NAME=value` that counts each word asked of it, and otherwise is that pattern."""

    def __init__(self, real: re.Pattern[str], work: Work) -> None:
        self.real, self.work = real, work

    def fullmatch(self, word: str):
        self.work.setting_checks += 1
        return self.real.fullmatch(word)

    def __getattr__(self, name: str):
        return getattr(self.real, name)


class CountedPattern:
    """A pattern of the splitter that counts what each call is handed. A pattern given the splitter's own line reads it in place
    and costs what it scans: the span of each match, or the whole line for a method that reads it all. A pattern given any other
    text is given a copy of part of the line, and costs the length of the copy, which a scan count does not see."""

    def __init__(self, real: re.Pattern[str], work: Work) -> None:
        self.real, self.work = real, work

    def charge(self, string: str, scanned: int) -> None:
        self.work.pattern_calls += 1
        self.work.pattern_chars += scanned if string is self.work.line else len(string)

    def finditer(self, string: str, pos: int = 0, endpos: int = sys.maxsize) -> Iterator[re.Match[str]]:
        in_place = string is self.work.line
        self.work.pattern_calls += 1
        self.work.pattern_chars += 0 if in_place else len(string)
        at = pos
        for found in self.real.finditer(string, pos, endpos):
            self.work.pattern_chars += found.end() - at if in_place else 0
            at = found.end()
            yield found

    def match(self, string: str, pos: int = 0, endpos: int = sys.maxsize) -> re.Match[str] | None:
        found = self.real.match(string, pos, endpos)
        self.charge(string, (found.end() if found else min(len(string), endpos)) - pos)
        return found

    def search(self, string: str, pos: int = 0, endpos: int = sys.maxsize) -> re.Match[str] | None:
        found = self.real.search(string, pos, endpos)
        self.charge(string, (found.end() if found else min(len(string), endpos)) - pos)
        return found

    def fullmatch(self, string: str, pos: int = 0, endpos: int = sys.maxsize) -> re.Match[str] | None:
        self.charge(string, min(len(string), endpos) - pos)
        return self.real.fullmatch(string, pos, endpos)

    def sub(self, repl, string: str, count: int = 0) -> str:
        self.charge(string, len(string))
        return self.real.sub(repl, string, count)

    def subn(self, repl, string: str, count: int = 0) -> tuple[str, int]:
        self.charge(string, len(string))
        return self.real.subn(repl, string, count)

    def findall(self, string: str, pos: int = 0, endpos: int = sys.maxsize) -> list:
        self.charge(string, min(len(string), endpos) - pos)
        return self.real.findall(string, pos, endpos)

    def split(self, string: str, maxsplit: int = 0) -> list:
        self.charge(string, len(string))
        return self.real.split(string, maxsplit)

    def __getattr__(self, name: str):
        return getattr(self.real, name)


@contextlib.contextmanager
def counting() -> Iterator[Work]:
    """Counts what the code under test does, and fails the call that falls back to `shlex`, which joins a word one character
    at a time. A queue the code reads from counts each word it takes from the front, and the splitter's patterns count the text
    they are handed."""
    work = Work()
    real_split = processes.split_words

    def split_words(line: str, **options) -> list[str]:
        work.splits += 1
        work.chars += len(line)
        work.line = line
        return real_split(line, **options)

    class Queue(deque):
        def popleft(self):
            work.pops += 1
            return super().popleft()

    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch.object(processes, "split_words", split_words))
        stack.enter_context(mock.patch.object(shlex, "shlex", side_effect=AssertionError("a caller went back to shlex")))
        stack.enter_context(mock.patch.dict(processes._WORDS, {punctuation: CountedPattern(real, work) for punctuation, real in processes._WORDS.items()}))
        for name in ("_UNQUOTE", "_DOUBLE_REST"):
            stack.enter_context(mock.patch.object(processes, name, CountedPattern(getattr(processes, name), work)))
        for module in (shell, commands, file_reads, file_writes):
            stack.enter_context(mock.patch.object(module, "deque", Queue))
            stack.enter_context(mock.patch.object(module, "SETTING", CountedSetting(module.SETTING, work)))
        yield work


def cost(call: Callable[[int], object], size: int) -> Work:
    """The work `call(size)` does."""
    with counting() as work:
        call(size)
    return work


def unbounded_backtracking(pattern: re.Pattern[str]) -> list[str]:
    """The repeats of a pattern that take as much as they can and give it back when the rest fails, with no end: each is a place
    where the engine may scan again. A possessive repeat never gives back. The parse tree `re.DEBUG` prints names each one."""
    re.purge()  # a pattern compiled before with this flag prints nothing
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        re.compile(pattern.pattern, pattern.flags | re.DEBUG)
    tree = printed.getvalue().split("\n\n")[0].splitlines()
    return [line.strip() for line in tree if line.strip().startswith(("MAX_REPEAT", "MIN_REPEAT")) and line.endswith("MAXREPEAT")]


def repeat_inside_repeat(group: str = "(") -> str:
    """The slow sample the readers of a pattern must find: a repeat of a group that holds a repeat. It is built here, so
    no such pattern sits in the source for a scanner to flag."""
    return "".join([group, "a", "+", ")", "+", "b"])


def runs_that_can_take_their_end(pattern: re.Pattern[str]) -> list[str]:
    """The runs of a pattern that take as much as they can and may give it back, and so may scan again: one inside another, one
    that ends the pattern, and one whose next piece is a character the run itself takes. A run stopped by a character it cannot
    take has one way to match, so no scan backs up over it. It reads the parse tree `re.DEBUG` prints."""
    re.purge()
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        re.compile(pattern.pattern, pattern.flags | re.DEBUG)
    nodes: list[list[str]] = []
    for line in printed.getvalue().split("\n\n")[0].splitlines():
        if line.startswith(" "):
            nodes[-1].append(line.strip())
        else:
            nodes.append([line])
    groups = {int(n[0].split()[1]): {int(c.split()[1]) for c in n[1:] if c.startswith("LITERAL")} for n in nodes if n[0].startswith("SUBPATTERN")}

    def unbounded(line: str) -> bool:
        return line.startswith(("MAX_REPEAT", "MIN_REPEAT")) and line.endswith("MAXREPEAT")

    def takes(body: list[str], code: int) -> bool:
        """Whether the class under a run's `IN` takes the character with this code."""
        inside = False
        for line in body:
            kind, _, arg = line.partition(" ")
            if kind == "LITERAL":
                inside |= int(arg) == code
            elif (kind, arg) == ("CATEGORY", "CATEGORY_SPACE"):
                inside |= chr(code).isspace()
            elif kind != "NEGATE":
                raise NotImplementedError(f"this reader does not know `{line}`")
        return inside != any(line.startswith("NEGATE") for line in body)

    problems = [f"{line}, inside another piece" for node in nodes for line in node[1:] if unbounded(line)]
    for at, node in enumerate(nodes):
        if not unbounded(node[0]):
            continue
        after = nodes[at + 1][0].partition(" ") if at + 1 < len(nodes) else ("", "", "")
        ends = {int(after[2])} if after[0] == "LITERAL" else groups[int(after[2])] if after[0] == "GROUPREF" else None
        body = node[2:] if node[1:2] == ["IN"] else node[1:2] if node[1:2] and node[1].startswith("LITERAL") else None
        if body is None or ends is None or any(takes(body, code) for code in ends):
            next_piece = f"{after[0]} {after[2]}" if after[0] else "the end of the pattern"
            problems.append(f"{node[0]}, before {next_piece}")
    return problems


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


SKIP_SHLEX = unittest.skipUnless(processes.POSSESSIVE_REPEATS_WORK, "this Python keeps shlex, which is slow on a long word by design")


class LinearCost(unittest.TestCase):
    """The step every cost test shares. A call given `GROWTH` times the input may do `GROWTH` times the work and no more: work
    that is a line's length times itself does `GROWTH` squared times."""

    def assertLinear(self, call: Callable[[int], object], counts: str, size: int = LONG):
        """`call(size)` does work in `counts` (a field of `Work`) that grows no faster than `size`. The sizes run smallest
        first and the first step that grows too fast ends the test, so a call that went back to work squared in its length
        fails at the small size and never runs the large one."""
        before = cost(call, size // GROWTH**2)
        self.assertGreater(getattr(before, counts), 0, f"the call did no `{counts}` work, so it no longer reads the way this test counts: {before}")
        for n in (size // GROWTH, size):
            after = cost(call, n)
            for counter in ("chars", "splits", "pattern_chars", "pattern_calls", "pops", "setting_checks"):
                self.assertLessEqual(getattr(after, counter), GROWTH * getattr(before, counter), f"{counter} at {n}: {before} then {after}")
            before = after


@SKIP_SHLEX
class SplitCostTests(LinearCost):
    """`split_words` scans each character once, never falls back to `shlex`, and never copies the rest of the line to read the
    next word. It runs on a line of one long word, of many words, and of many pieces."""

    def test_one_long_word(self):
        shapes = {
            "plain": lambda n: ("x" * n, ["x" * n]),
            "single quotes": lambda n: ("'" + "x" * n + "'", ["x" * n]),
            "double quotes with escapes": lambda n: ('"' + "x\\\\" * (n // 3) + '"', ["x\\" * (n // 3)]),
            "escaped characters": lambda n: ("\\a" * (n // 2), ["a" * (n // 2)]),
        }
        for name, shape in shapes.items():
            for punctuation in (False, True):
                with self.subTest(shape=name, punctuation=punctuation):
                    self.assertLinear(lambda n, shape=shape, punctuation=punctuation: ours(shape(n)[0], punctuation), "pattern_calls")
                    line, words = shape(LONG)
                    self.assertEqual(ours(line, punctuation), ("words", words))
        for punctuation in (False, True):
            with self.subTest(shape="a quote left open", punctuation=punctuation):
                self.assertLinear(lambda n, punctuation=punctuation: ours("'" + "x" * n, punctuation), "pattern_calls")
                self.assertEqual(ours("'" + "x" * LONG, punctuation), ("error", "No closing quotation"))

    def test_many_words_and_many_pieces(self):
        """Each shape has as many words or pieces as `n`, so a splitter that copies the rest of the line at each one does work
        that is `n` squared, and `pattern_chars` shows it."""
        shapes = {
            "words": (lambda n: "a " * n, True, lambda n: ["a"] * n),
            "words with no punctuation": (lambda n: "a " * n, False, lambda n: ["a"] * n),
            "quoted words": (lambda n: "'a b' " * n, False, lambda n: ["a b"] * n),
            "pieces of one word": (lambda n: "'a'" * n, True, lambda n: ["a" * n]),
            "words and marks": (lambda n: "a;" * n, True, lambda n: ["a", ";"] * n),
        }
        for name, (line, punctuation, words) in shapes.items():
            with self.subTest(shape=name):
                self.assertLinear(lambda n, line=line, punctuation=punctuation: ours(line(n), punctuation), "pattern_chars", MANY)
                self.assertEqual(ours(line(LONG), punctuation), ("words", words(LONG)))

    def test_no_pattern_of_the_splitter_can_scan_again(self):
        """The time of a pattern is spent in the engine, where no counter reaches. The splitter's patterns make every repeat
        possessive, so none gives back what it took, and the engine never scans a character twice."""
        patterns = {
            "words": processes._WORDS[False],
            "words with punctuation": processes._WORDS[True],
            "unquote": processes._UNQUOTE,
            "double quote rest": processes._DOUBLE_REST,
        }
        for name, pattern in patterns.items():
            with self.subTest(name):
                self.assertEqual(unbounded_backtracking(pattern), [])

    def test_the_reader_of_a_pattern_finds_a_repeat_that_scans_again(self):
        self.assertEqual(len(unbounded_backtracking(re.compile(repeat_inside_repeat()))), 2)
        self.assertEqual(unbounded_backtracking(re.compile(r"(?:a*+b)++")), [])
        self.assertEqual(unbounded_backtracking(re.compile(r"a{0,3}b?")), [])


@SKIP_SHLEX
class EachCallerIsLinearTests(LinearCost):
    """Each fails when its caller goes back to `shlex.split`, splits the rest of the line again at each word, or takes the
    front of a list that holds the words, which `deque` avoids."""

    def test_the_command_pattern_reader(self):
        self.assertLinear(lambda n: commands.normalize("echo " + "x" * n), "chars")

    def test_the_other_repository_reader(self):
        self.assertLinear(lambda n: commands.names_another_repository("git " + "x" * n), "chars")
        self.assertLinear(lambda n: commands.names_another_repository("git " + "-p " * n + "push"), "pops", LONG // 16)

    def test_the_folder_reader(self):
        self.assertLinear(lambda n: commands.folder_after("cd " + "x" * n, "/"), "chars")

    def test_a_whole_command_level(self):
        """A line of one long word and a line of many words, so the splitter and what reads its words each stay linear."""
        rules = risk.rule_set(None)
        self.assertLinear(lambda n: risk.command_level(rules, "echo " + "x" * n, cwd=None), "chars")
        self.assertLinear(lambda n: risk.command_level(rules, "echo " + "x " * n, cwd=None), "pattern_chars", MANY)

    def test_the_delegated_command_reader(self):
        self.assertLinear(lambda n: delegated.words("git push origin " + "x" * n), "chars")

    def test_the_launcher_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            launcher = Path(tmp) / "aidd"

            def read(n: int):
                launcher.write_text("#!/bin/sh\nexec " + "x" * n + ' "$@"\n', encoding="utf-8")
                return mcp_wiring.launcher_problem(launcher)

            self.assertLinear(read, "chars")

    def test_the_operator_command_splitter(self):
        self.assertLinear(lambda n: processes.split_command("x" * n, windows=False), "chars")

    def test_a_line_of_many_settings_or_redirections(self):
        """A list emptied from the front costs time squared in its length: 250,000 words took seconds."""
        words = 250_000
        self.assertLinear(lambda n: shell.tokens("A=1 " * n + "x"), "setting_checks", words)
        self.assertLinear(lambda n: shell.without_redirections("echo " + "x " * n), "pops", words)

    def test_a_reader_with_many_options(self):
        """`grep` re-read its rest of the line at every option: 20,000 options took seconds."""
        rules = risk.rule_set(None)
        self.assertLinear(lambda n: commands.file_read_actions(rules, "grep " + "-i " * n + "x f"), "pops", 20_000)

    def test_a_writer_with_many_words_or_many_redirections(self):
        """The files a command writes are read from a queue of its words, whatever their number."""
        rules = risk.rule_set(None)

        def writes(line: str) -> object:
            return file_writes.Writes(rules, None, None).part((line,), commands.normalize)

        self.assertLinear(lambda n: writes("sed " + "-i " * n + "x f"), "pops", 20_000)
        self.assertLinear(lambda n: writes("tee " + "f " * n), "pops", 20_000)
        self.assertLinear(lambda n: writes("echo " + "> f " * n), "pops", 20_000)
        self.assertLinear(lambda n: writes("cp -r " + "d " * n + "e"), "pops", 20_000)


class ReadersKeepTheirShapeTests(unittest.TestCase):
    """Readers whose shape the cost tests lean on. None measures a cost or needs the fast splitter, so each runs on every Python."""

    def test_the_escaped_key_reader(self):
        """A quoted key's two runs around a backslash backed up over every backslash: 48,000 characters took 4 s. The first run
        cannot take a backslash, so the backslash that ends it is fixed and the second run is read once."""
        self.assertEqual(runs_that_can_take_their_end(diff_signals.ESCAPED_KEY), [])
        for line, escaped in (('  "envi\\x72onment": prod', True), ("{'a\\b': 1}", True), ('  "environment": prod', False), ("run: 'a\\b'", False)):
            with self.subTest(line):
                self.assertEqual(bool(diff_signals.ESCAPED_KEY.search(line)), escaped)

    def test_the_reader_of_runs_finds_a_run_that_can_take_its_end(self):
        for pattern, expected in (
            (r"""(["'])[^"'\\]*\\[^"']*\1""", 0),  # the first run stops at the backslash, the second at the quote it opened with
            (r"""(["'])[^"']*\\[^"']*\1""", 1),  # the first run takes the backslash that ends it, so it backs up over each one
            (r"a*b", 0),
            (r"a*a", 1),
            (r"\s*:", 0),
            (r"[^:]*", 1),  # nothing ends it
            (repeat_inside_repeat("(?:"), 2),
        ):
            with self.subTest(pattern):
                self.assertEqual(len(runs_that_can_take_their_end(re.compile(pattern))), expected)

    def test_no_list_of_the_words_is_emptied_from_the_front(self):
        """Taking the first item of a list moves every other item, which no counter reaches, so the words of a line are taken
        from a queue, or read by their place. These modules read every word of a long line."""
        for module in (shell, commands, file_writes):
            tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            first = lambda node: isinstance(node, ast.Constant) and node.value == 0  # noqa: E731
            found = [
                node.lineno
                for node in ast.walk(tree)
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "pop"
                    and len(node.args) == 1
                    and first(node.args[0])
                )
                or (isinstance(node, ast.Delete) and any(isinstance(t, ast.Subscript) and first(t.slice) for t in node.targets))
            ]
            with self.subTest(module=module.__name__):
                self.assertEqual(found, [], "lines that take the first item of a list")

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
