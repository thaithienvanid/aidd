"""One question, "is this a glob", has one answer. The path matcher reads `*` and `?` as wildcards and a bracket as itself, so
every place that tells a pattern from a path asks `globs.is_pattern`. The route of planned paths and the scope of a new Spec once
disagreed about `[`: the scope counted it as a glob, the route did not. For every generated path, each decider gives the answer
the matcher gives."""

import itertools
import re
import unittest

import helpers  # noqa: F401  (puts src on sys.path)

from aidd import workitems
from aidd.kernel import globs
from aidd.risk import routes
from helpers import ROOT

TOKENS = ["m", "*", "?", "[", "]", "[ab]", "**", ".py", "-", "é"]


def generated_paths() -> list[str]:
    """`src/` and one to three tokens: every wildcard, bracket, and ordinary piece in every position, in a fixed order."""
    return [f"src/{''.join(parts)}" for size in (1, 2, 3) for parts in itertools.product(TOKENS, repeat=size)]


class OneAnswerToIsItAGlob(unittest.TestCase):
    def test_the_route_and_the_scope_agree_with_the_matcher_on_every_generated_path(self):
        for path in generated_paths():
            glob = globs.is_pattern(path)
            route_reads_a_glob = routes.planned_paths([path], []) != [path]
            scope_reads_a_glob = workitems.folder_scope([path], set()) == [path]
            if route_reads_a_glob != glob or scope_reads_a_glob != glob:
                self.fail(f"{path!r}: the matcher says glob={glob}, the route says {route_reads_a_glob}, the scope says {scope_reads_a_glob}")

    def test_the_decision_rests_on_the_matcher_which_reads_a_bracket_as_itself(self):
        """Why `[` is not a wildcard: the matcher compares it literally, so `src/[id]/page.tsx` names that one file, and treating it as
        a pattern would only keep a file from being widened to its folder like any other."""
        self.assertTrue(globs.match("src/[id]/page.tsx", "src/[id]/page.tsx"))
        self.assertFalse(globs.match("src/[id]/page.tsx", "src/i/page.tsx"))
        self.assertTrue(globs.match("src/[a-z]/*.py", "src/[a-z]/x.py"))
        self.assertFalse(globs.is_pattern("src/[id]/page.tsx"))
        self.assertTrue(globs.is_pattern("src/*/page.tsx") and globs.is_pattern("src/?/page.tsx"))

    def test_the_two_deciders_can_be_told_apart_when_one_is_broken(self):
        """The comparison fails for a decider that counts `[`: the bracket path is where it would differ."""
        counts_brackets = lambda p: any(c in p for c in "*?[")  # noqa: E731
        differing = [p for p in generated_paths() if counts_brackets(p) != globs.is_pattern(p)]
        self.assertIn("src/[", differing)
        self.assertTrue(all("[" in p for p in differing))

    def test_no_place_spells_the_wildcard_test_itself(self):
        """A wildcard test written inline is a second decider that can drift. `src/aidd/delegation/diff_signals.py` still has two,
        which its own change converts; the rest of the source asks `globs.is_pattern`."""
        inline = re.compile(r'for c in ("[*?]+\[?"|_WILD)')
        found = [
            f"{path.relative_to(ROOT).as_posix()}:{n}"
            for path in sorted((ROOT / "src" / "aidd").rglob("*.py"))
            if path.name != "globs.py"
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if inline.search(line)
        ]
        self.assertEqual([f for f in found if not f.startswith("src/aidd/delegation/diff_signals.py:")], [], "ask `globs.is_pattern`")


if __name__ == "__main__":
    unittest.main()
