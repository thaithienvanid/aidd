"""Seeded fuzzing of the parsing the gate decides with: hostile input may be rejected, never crash it.

TOML itself is parsed by the standard library's tomllib; what aidd writes by hand is the front-matter
splitter, the Change Request block finder (fences, HTML comments, quotes), and the glob engine. The runtime
has no dependencies, so this is a small deterministic generator rather than a fuzzing framework: fixed
seeds, bounded iterations, and inputs built from the characters each parser treats specially. A crash
here would surface in production as an `internal` failure on a pull request.
"""

import random
import string
import unittest

from helpers import ROOT  # noqa: F401  (puts src on sys.path)

from aidd import globs, model

ITERATIONS = 1500
TOML_ALPHABET = "[]{}=\".,#\n\t \\'" + "abc_-0123456789" + "é‮"
GLOB_ALPHABET = "*?[]!/\\.{},-" + "ab/"
BODY_PIECES = ["```toml aidd\n", "```\n", "````\n", "~~~\n", "<!--", "-->", "\n", 'route = "minor"\n', 'spec = "x"\n', "> ", "    ", "```toml\n"]


def text(rng: random.Random, alphabet: str, n: int) -> str:
    return "".join(rng.choice(alphabet) for _ in range(rng.randint(0, n)))


class ParserFuzzTests(unittest.TestCase):
    def test_front_matter_rejects_or_parses_never_crashes(self):
        rng = random.Random(2)
        for _ in range(ITERATIONS):
            src = rng.choice(["+++\n", "---\n", "﻿+++\n", ""]) + text(rng, TOML_ALPHABET, 40) + rng.choice(["\n+++\n", "\n---\n", ""]) + "body"
            try:
                data, body = model.split_front_matter(src, "fuzz")
                self.assertIsInstance(data, dict)
            except model.ModelError:
                pass

    def test_change_block_finder_never_crashes(self):
        rng = random.Random(3)
        for _ in range(ITERATIONS):
            body = "".join(rng.choice(BODY_PIECES) for _ in range(rng.randint(0, 12)))
            data, errors = model.parse_change_block(body)
            self.assertTrue(data is None or isinstance(data, dict))
            self.assertIsInstance(errors, list)

    def test_glob_functions_never_crash(self):
        rng = random.Random(4)
        for _ in range(ITERATIONS):
            pattern, other = text(rng, GLOB_ALPHABET, 12), text(rng, GLOB_ALPHABET, 12)
            path = text(rng, string.ascii_lowercase + "/.", 16)
            globs.match(pattern, path)
            globs.match(pattern, path, fold_case=True)
            globs.is_catch_all(pattern)
            globs.overlap(pattern, other)
            globs.literal_prefix(pattern)

    def test_toml_errors_surface_as_model_errors(self):
        rng = random.Random(1)
        for _ in range(ITERATIONS):
            try:
                self.assertIsInstance(model.parse_toml(text(rng, TOML_ALPHABET, 60), "fuzz"), dict)
            except model.ModelError:
                pass


if __name__ == "__main__":
    unittest.main()
