"""A Spec's title is the commit subject `aidd ship` writes (`<type>: <title> (<ID>)`), so it is short: Git's convention
keeps a subject within 72 characters."""

import unittest
from pathlib import Path

from helpers import ROOT  # noqa: F401  (puts src on the path)

from aidd.workitems import spec_warnings


class TitleSubjectTests(unittest.TestCase):
    def test_a_long_title_warns(self):
        long = {"id": "SPEC-12", "type": "feat", "title": "Rate-limit every authenticated checkout request per card and per account, with a retry header"}
        found = spec_warnings.size_warnings(Path("specs/SPEC-12.md"), "", long)
        self.assertTrue(any("commit subject" in w for w in found), found)
        short = dict(long, title="Rate-limit authenticated checkout")
        self.assertFalse(any("commit subject" in w for w in spec_warnings.size_warnings(Path("specs/SPEC-12.md"), "", short)))


if __name__ == "__main__":
    unittest.main()
