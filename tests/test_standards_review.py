"""The registry check counts its dated entries by type."""

from __future__ import annotations

import unittest

from helpers import run_cli

from aidd import knowledge


class StandardsReviewTests(unittest.TestCase):
    def test_the_counts_name_each_type(self):
        entries = knowledge.dated_entries()
        ids = len({s["id"] for s in entries if s.get("id")})
        extensions = sum(1 for s in entries if not s.get("id") and s["where"].startswith("extension "))
        skills = len(entries) - extensions - sum(1 for s in entries if s.get("id"))
        _, out = run_cli("eval", "standards")
        self.assertIn(f"{len(entries)} dated applications: {ids} registry standards applied ", out)
        self.assertIn(f"times, {extensions} extensions, and {skills} practice skills", out)


if __name__ == "__main__":
    unittest.main()
