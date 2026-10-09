"""Repository consistency: this repository's own files agree with what generates and validates them.

These tests fail after an edit that forgot `aidd gen-docs` or left an invalid Spec, not after a code bug. Run them
alone, with the registry and document hygiene checks, with:

    python3 -m unittest discover -s tests -k RepositoryConsistency -k registry_hygiene
"""

import contextlib
import unittest

from helpers import IN_GIT_CHECKOUT, ROOT, run_cli

from aidd import docs


class RepositoryConsistencyTests(unittest.TestCase):
    def test_generated_blocks_are_current(self):
        self.assertEqual([str(p) for p in docs.gen_docs(ROOT, check=True)], [])
        code, out = run_cli("gen-docs", "--check")  # the command CI runs says the same
        self.assertEqual(code, 0, out)

    @unittest.skipUnless(IN_GIT_CHECKOUT, "validate reads this repository's git state")
    def test_this_repository_validates(self):
        with contextlib.chdir(ROOT):
            code, out = run_cli("validate")
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
