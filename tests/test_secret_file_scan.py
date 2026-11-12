"""The secret scan of a file reads it whole first and line by line only when it must, and gives the answer the line-by-line reading gave.

Invariant: for every text, `secret_patterns.file_secret_types(text)` is what reading each line with `secret_types` gives, in the order
the lines first show each type. The whole-text check may only skip a text that holds nothing, so a secret it could miss (past the line
cap, behind a fullwidth letter, after a form feed) is still found. The cost is counted in line reads, never timed.

Secret-shaped values are joined from pieces here, so no literal of one sits in the repository."""

from __future__ import annotations

import random
import unicodedata
import unittest
from unittest import mock

import helpers  # noqa: F401  (puts src on the path)

from aidd.kernel import secret_patterns

GITHUB = "gh" + "p_" + "a1B2" * 9
AWS = "AK" + "IA" + "ABCDEFGHIJKLMNOP"
SLACK = "xox" + "b-" + "1234567890-abcdef"
ASSIGNMENT = "API_SE" + "CRET=" + "hunter2pass"
KEY_HEADER = "-----BEGIN RSA PRI" + "VATE KEY-----"
JWT = "ey" + "J" + "a" * 12 + ".ey" + "J" + "b" * 12 + "." + "c" * 12
FULLWIDTH_GITHUB = "".join(chr(ord(c) + 0xFEE0) if c.isascii() and c.isalnum() or c == "_" else c for c in GITHUB)
ZERO_WIDTH_GITHUB = GITHUB[:8] + chr(0x200B) + GITHUB[8:]
# Characters written as code points, so no invisible one sits in this file's text.
LINE_SEPARATOR, PARAGRAPH_SEPARATOR, NO_BREAK_SPACE = chr(0x2028), chr(0x2029), chr(0xA0)
CAFE = "caf" + chr(0xE9)


def line_by_line(text: str) -> list[str]:
    """The reading the scan had before it looked at the whole text: each line alone, each type once, in first-seen order."""
    shapes: list[str] = []
    for line in text.splitlines():
        shapes += [k for k in secret_patterns.secret_types(line) if k not in shapes]
    return shapes


def comparable_before(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", text) if unicodedata.category(c) != "Cf")


CASES = {
    "empty": "",
    "one clean line": "x = 1\n",
    "a clean file with no final break": "x = 1\ny = 2",
    "one token": f"token = '{GITHUB}'\n",
    "a token on the last line": f"a\nb\n{AWS}",
    "two types, the later pattern first": f"{SLACK}\n{AWS}\n",
    "two types, the earlier pattern first": f"{AWS}\n{SLACK}\n",
    "one type twice": f"{AWS}\n{AWS}\n",
    "a windows line break": f"a\r\n{GITHUB}\r\nb\r\n",
    "a lone carriage return": f"a\r{GITHUB}\rb",
    "a form feed between lines": f"a\x0c{AWS}\x0cb",
    "a vertical tab between lines": f"{ASSIGNMENT}\x0bx",
    "a next-line character": f"{SLACK}\x85{AWS}",
    "a line separator": f"{AWS}{LINE_SEPARATOR}{SLACK}",
    "an assignment whose value is on the next line": "API_SE" + "CRET=\nhunter2pass\n",
    "a private key header": f"{KEY_HEADER}\nMIIabc\n",
    "a private key header split by a line break": "-----BEGIN RSA PRI\nVATE KEY-----\n",
    "a json web token": f"{JWT}\n",
    "a json web token split by a line break": JWT.replace(".", "\n", 1),
    "a token past the line cap": "x" * 5000 + f" {GITHUB}\n",
    "a token that starts before the line cap and ends past it": "x" * (secret_patterns.MAX_SECRET_LINE - 12) + f" {AWS}\n",
    "a token whose last character is the cap's last": "x" * (secret_patterns.MAX_SECRET_LINE - len(AWS)) + f"{AWS}\n",
    "a token cut by the cap that a longer word hides": "x" * (secret_patterns.MAX_SECRET_LINE - len(AWS)) + f"{AWS}zzzz\n",
    "a long clean line": "y" * 9000 + "\n",
    "a token behind a fullwidth letter": f"{FULLWIDTH_GITHUB}\n",
    "a token split by a zero-width space": f"{ZERO_WIDTH_GITHUB}\n",
    "a clean line with a non-ASCII word": f"{CAFE} {chr(0x2014)} done\n",
    "a non-ASCII line before a token": f"{CAFE}\n{AWS}\n",
    "a control character": f"a\x00b\x1f\n{SLACK}\n",
}


def generated(count: int = 1500) -> list[str]:
    """Texts joined at random from secret-shaped pieces, noise, and every line separator `splitlines` knows."""
    rng = random.Random(20261113)
    pieces = [
        GITHUB,
        AWS,
        SLACK,
        ASSIGNMENT,
        KEY_HEADER,
        JWT,
        FULLWIDTH_GITHUB,
        ZERO_WIDTH_GITHUB,
        "plain words",
        "x = 1",
        "",
        CAFE,
        "API_SE" + "CRET=",
        "hunter2pass",
    ]
    separators = ["\n", "\r\n", "\r", "\x0b", "\x0c", "\x1c", "\x85", LINE_SEPARATOR, PARAGRAPH_SEPARATOR, " ", "="]
    texts = []
    for _ in range(count):
        out = []
        for _ in range(rng.randint(0, 8)):
            piece = rng.choice(pieces)
            if rng.random() < 0.05:
                piece = "z" * rng.choice([secret_patterns.MAX_SECRET_LINE - 8, secret_patterns.MAX_SECRET_LINE, secret_patterns.MAX_SECRET_LINE + 5]) + piece
            out += [piece, rng.choice(separators)]
        texts.append("".join(out))
    return texts


class AFileIsReadWholeFirstAndGivesTheLineByLineAnswerTests(unittest.TestCase):
    def test_the_answer_is_the_line_by_line_answer_for_every_case(self):
        for name, text in CASES.items():
            with self.subTest(name):
                self.assertEqual(secret_patterns.file_secret_types(text), line_by_line(text))

    def test_the_answer_is_the_line_by_line_answer_for_generated_texts(self):
        texts = generated()
        found = [line_by_line(text) for text in texts]
        self.assertTrue(any(found), "the control: some generated text holds a secret")
        self.assertTrue(any(not f for f in found), "the control: some generated text holds none")
        for text, expected in zip(texts, found, strict=True):
            self.assertEqual(secret_patterns.file_secret_types(text), expected, repr(text[:200]))

    def test_the_table_has_texts_the_whole_check_alone_would_get_wrong(self):
        """The control: a reading that trusted the whole-text answer would differ on these, so the table can fail."""
        past_the_cap = CASES["a token past the line cap"]
        self.assertEqual(line_by_line(past_the_cap), [])
        self.assertTrue(any(rx.search(past_the_cap) for _, rx in secret_patterns.SECRET_PATTERNS))
        order = CASES["two types, the later pattern first"]
        self.assertEqual(line_by_line(order), ["a Slack token", "an AWS access key id"])
        self.assertEqual([t for t, rx in secret_patterns.SECRET_PATTERNS if rx.search(order)], ["an AWS access key id", "a Slack token"])


class Counted:
    """A pattern that counts its searches."""

    def __init__(self, rx, counts: list[int]):
        self.rx, self.counts = rx, counts

    def search(self, text: str):
        self.counts.append(1)
        return self.rx.search(text)


class AFileCostsOnlyTheSearchesOfThePatternsItCouldMatchTests(unittest.TestCase):
    def searches(self, text: str) -> int:
        counts: list[int] = []
        counted = tuple((name, Counted(rx, counts)) for name, rx in secret_patterns.SECRET_PATTERNS)
        with mock.patch.object(secret_patterns, "SECRET_PATTERNS", counted):
            secret_patterns.file_secret_types(text)
        return len(counts)

    def test_a_clean_text_is_searched_by_no_pattern_however_many_lines_it_has(self):
        for name, text in {
            "ascii": "".join(f"value_{n} = {n}\n" for n in range(500)),
            "non-ASCII": "".join(f"{CAFE}_{n} = {n}\n" for n in range(500)),
            "a long line": "y" * 9000 + "\n",
            "empty": "",
        }.items():
            with self.subTest(name):
                self.assertEqual(self.searches(text), 0)

    def test_a_text_is_searched_by_the_pattern_whose_text_it_holds_and_by_no_other(self):
        self.assertEqual(self.searches("an AK" + "IA but no key\n"), 1)
        self.assertEqual(self.searches("an AK" + "IA and a Slack hooks.slack.com/ but no key\n"), 2)

    def test_a_text_with_a_secret_is_read_line_by_line_too(self):
        for name in ("one token", "a token behind a fullwidth letter", "two types, the later pattern first"):
            with self.subTest(name):
                text = CASES[name]
                self.assertTrue(secret_patterns.file_secret_types(text))
                self.assertGreater(self.searches(text), 1)


# A match of every branch of each strict pattern, joined from pieces so no secret-shaped literal sits in this file.
SAMPLES = {
    "an AWS access key id": [AWS, "AS" + "IA" + "ABCDEFGHIJKLMNOP"],
    "a Stripe live key": ["sk_" + "live_" + "A" * 20, "rk_" + "live_" + "A" * 20],
    "a GitHub token": [GITHUB, *(f"gh{kind}_" + "a1B2" * 9 for kind in "ousr"), "github_" + "pat_" + "a" * 30],
    "a GitLab token": ["glpat-" + "a" * 20],
    "a Slack token": [SLACK, *(f"xox{kind}-" + "1234567890-abc" for kind in "apos" + "r")],
    "a Slack webhook": ["hooks.slack.com/" + kind + "/" + "A" * 24 for kind in ("services", "workflows")],
    "an OpenAI or Anthropic key": ["sk-" + "a" * 24, *("sk-" + kind + "-" + "a" * 24 for kind in ("ant", "proj", "svcacct", "admin"))],
    "a Google API key": ["AI" + "za" + "a" * 35],
    "an npm token": ["npm_" + "a" * 36],
    "a JSON web token": [JWT],
    "a private key": [KEY_HEADER, "-----BEGIN " + "PRIVATE KEY-----"],
    "a *_SECRET assignment": [ASSIGNMENT, "X_SE" + "CRET_KEY: 'abcdefgh1'"],
}


class EveryPatternHasTheTextItsMatchMustHoldTests(unittest.TestCase):
    """The ground of the pre-check: a match of a pattern holds one of the texts in `_NEEDS`, so a text without them is not searched."""

    def test_every_strict_pattern_has_a_row_and_no_row_is_left_over(self):
        self.assertEqual(sorted(secret_patterns._NEEDS), sorted(name for name, _ in secret_patterns.SECRET_PATTERNS))
        self.assertEqual(sorted(SAMPLES), sorted(secret_patterns._NEEDS), "the control: a sample for each pattern")

    def test_every_branch_of_every_pattern_holds_a_text_of_its_row(self):
        for name, rx in secret_patterns.SECRET_PATTERNS:
            for sample in SAMPLES[name]:
                with self.subTest(name, sample=sample[:30]):
                    self.assertTrue(rx.search(sample), "the control: the sample is a match")
                    self.assertTrue(any(lit in sample for lit in secret_patterns._NEEDS[name]))

    def test_no_generated_text_matches_a_pattern_without_its_text(self):
        rng = random.Random(20261114)
        samples = [sample for each in SAMPLES.values() for sample in each]
        pieces = [
            *samples,
            *(sample[: rng.randint(2, 8)] for sample in samples for _ in range(3)),
            "a" * 20,
            "A" * 20,
            "0" * 36,
            "-",
            "_",
            ".",
            "=",
            ":",
            " ",
            "/",
            '"',
            "x",
        ]
        matched = 0
        for _ in range(4000):
            text = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 6)))
            for name, rx in secret_patterns.SECRET_PATTERNS:
                if rx.search(text):
                    matched += 1
                    self.assertTrue(any(lit in text for lit in secret_patterns._NEEDS[name]), (name, text))
        self.assertGreater(matched, 100, "the control: some generated text matches a pattern")


class AnAsciiTextIsItsOwnComparableReadingTests(unittest.TestCase):
    def test_every_ascii_character_reads_as_it_did_through_normalization(self):
        every = "".join(chr(n) for n in range(128))
        self.assertEqual(secret_patterns.comparable(every), comparable_before(every))
        self.assertEqual(secret_patterns.comparable(every), every)

    def test_an_ascii_text_is_not_normalized_and_any_other_is(self):
        """The cost: normalization walks each character, so it runs only where it can change the text."""
        with mock.patch.object(secret_patterns.unicodedata, "normalize", wraps=unicodedata.normalize) as normalized:
            secret_patterns.comparable("value = 1\n" * 100)
            self.assertEqual(normalized.call_count, 0)
            secret_patterns.comparable(CAFE)
            self.assertEqual(normalized.call_count, 1)

    def test_a_text_with_a_non_ascii_character_is_still_normalized_and_stripped(self):
        for text in (FULLWIDTH_GITHUB, ZERO_WIDTH_GITHUB, CAFE, f"a{NO_BREAK_SPACE}b", ""):
            with self.subTest(text=text):
                self.assertEqual(secret_patterns.comparable(text), comparable_before(text))
        self.assertEqual(secret_patterns.comparable(FULLWIDTH_GITHUB), GITHUB)
        self.assertEqual(secret_patterns.comparable(ZERO_WIDTH_GITHUB), GITHUB)


if __name__ == "__main__":
    unittest.main()
