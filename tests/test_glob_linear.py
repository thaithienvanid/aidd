"""The glob matcher runs in time linear in pattern and path, and refuses overlong patterns.

A regex translation of `**` backtracks catastrophically: `**a` repeated a dozen times against forty `a`s took about a
minute. Patterns come from the config and from the change's own Spec (scope, test files), so a change could stall
the gate job with one line.
"""

import subprocess
import sys
import unittest

from helpers import ROOT

from aidd import globs

PROBE = """
import sys, time
sys.path.insert(0, {src!r})
from aidd import globs
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


if __name__ == "__main__":
    unittest.main()
