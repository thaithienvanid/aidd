"""The glob matcher runs in time linear in pattern and path, and refuses overlong patterns.

A regex translation of `**` backtracks catastrophically: `**a` repeated a dozen times against forty `a`s took about a
minute. Patterns come from the config and from the change's own Spec (scope, test files), so a change could stall
`aidd test` or `aidd validate` with one line.
"""

import itertools
import re
import subprocess
import sys
import unittest

from helpers import ROOT

from aidd.kernel import globs

PROBE = """
import sys, time
sys.path.insert(0, {src!r})
from aidd.kernel import globs
t = time.monotonic()
for pattern, path in (("**a" * 12 + "b", "a" * 40), ("**a" * 150 + "b", "a" * 4000), ("*a" * 200 + "b", "a" * 400)):
    assert not globs.match(pattern, path)
print(time.monotonic() - t)
"""


class GlobLinearTimeTests(unittest.TestCase):
    def test_adversarial_patterns_finish_in_under_a_second(self):
        try:
            p = subprocess.run([sys.executable, "-c", PROBE.format(src=str(ROOT / "src"))], capture_output=True, text=True, encoding="utf-8", timeout=15)
        except subprocess.TimeoutExpired:
            self.fail("the glob matcher backtracked: adversarial patterns did not finish in 15s")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertLess(float(p.stdout.strip()), 1.0)

    def test_an_overlong_pattern_is_refused_with_a_clear_error(self):
        self.assertFalse(globs.match("a" * globs.MAX_PATTERN_LENGTH, "b"))
        with self.assertRaises(globs.GlobError) as cm:
            globs.match("a" * (globs.MAX_PATTERN_LENGTH + 1), "a")
        self.assertIn("limit is 512", str(cm.exception))
        self.assertIsInstance(cm.exception, ValueError)

    def test_semantics_are_unchanged(self):
        cases = [
            ("**/*.py", "a/b/c.py", True),
            ("**/*.py", "c.py", True),
            ("a**b", "a/x/b", True),
            ("a*b", "a/b", False),
            ("src/?", "src/x", True),
            ("src/?", "src/", False),
            ("docs/", "docs/a/b", True),
            ("docs/**/", "docs", True),
            ("SRC/x", "src/x/y", False),
        ]
        for pattern, path, want in cases:
            self.assertEqual(globs.match(pattern, path), want, (pattern, path))
        self.assertTrue(globs.match("SRC/x", "src/x/y", fold_case=True))


TEXT_PROBE = """
import sys
sys.path.insert(0, {src!r})
from aidd import risk
from aidd.kernel import globs
assert not globs.match_text('*a*a*a*a*a*a*b', 'a' * 60000)
assert not globs.match_text('*?b', 'a' * 300000, segments=True)
assert not globs.match_text('*/?x?b', 'a/' * 150000, segments=True)
rs = risk.rule_set(None)
for line in ('gh api repos/o/r/dispatches -f \\'x=' + 'dispatches ' * 2500 + '\\'', 'aidd ' * 6000, 'gh workflow run ' + 'release ' * 4000):
    risk.command_level(rs, line)
"""


class TextGlobTests(unittest.TestCase):
    """One glob matcher for the command patterns and the endpoints (`match_text`): the same answers as a regular
    expression, in time that grows with the text."""

    def test_it_answers_as_a_regular_expression_does(self):
        patterns = ["".join(p) for n in range(1, 6) for p in itertools.product("ab*", repeat=n)]
        texts = ["".join(t) for n in range(0, 7) for t in itertools.product("ab", repeat=n)]
        for pattern in patterns:
            regex = re.compile(".*".join(re.escape(piece) for piece in pattern.split("*")), re.S)
            for text in texts:
                if globs.match_text(pattern, text) != (regex.fullmatch(text) is not None):
                    self.fail(f"{pattern!r} on {text!r}")

    def test_a_segment_is_one_whole_segment_up_to_a_slash_or_a_space(self):
        cases = [
            ("repos/?/?", "repos/o/r", True),
            ("repos/?/?", "repos/o/r/issues/comments/1", False),
            ("repos/?/?", "repos/o", False),
            ("repos/?/?", "repos/o/", False),
            ("repos/?/?", "repos/o/r x", False),
            ("*repos/?/?", "https://api.github.com/repos/o/r", True),
            ("*repos/?/?", "https://api.github.com/repos/o/r/issues", False),
            ("*repos/?/?*", "https://api.github.com/repos/o/r/issues", True),
            ("a/?/c*d", "a/bb/c-d", True),
            ("a/?/c*d", "a/b/c", False),
            ("a?b*c?", "axb-cy", False),  # a segment starts after `/`, a space, or the start, never inside a word
            ("*?b", "ab", False),  # the segment is the whole word, so a letter cannot follow it
            ("*?b", "a/b", False),
            ("x*?b", "xab", False),
            ("x*/?b", "xa/cb", False),
            ("x*/?", "xa/cb", True),
            ("a/??/c", "a/b/c", True),  # a run of them is one segment
            # A `?` followed by a letter is no whole segment, so it matches nothing.
            ("repos/?x*", "repos/axbx/y", False),
            ("repos/?x*", "repos/ax", False),
            ("repos/?x", "repos/ax", False),
            ("repos/? x", "repos/a x", True),
        ]
        for pattern, text, want in cases:
            with self.subTest(pattern=pattern, text=text):
                self.assertEqual(globs.match_text(pattern, text, segments=True), want)
        self.assertTrue(globs.match_text("a?b", "a?b"))  # without `segments`, a `?` is itself
        self.assertFalse(globs.match_text("a?b", "axb"))

    def test_a_long_text_takes_no_time_to_refuse(self):
        """With several `*`, a regular expression tries every split of the text: this hangs without the matcher."""
        try:
            done = subprocess.run(
                [sys.executable, "-c", TEXT_PROBE.format(src=str(ROOT / "src"))], capture_output=True, text=True, encoding="utf-8", timeout=15
            )
        except subprocess.TimeoutExpired:
            self.fail("the text matcher backtracked: long texts did not finish in 15s")
        self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == "__main__":
    unittest.main()
