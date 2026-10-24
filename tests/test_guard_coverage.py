"""Where the guard runs is one fact: the harness data says which agents get it as their own hook, and every page that
names them is generated from it. The other agents get the instructions and the gate, never a claimed guard."""

from __future__ import annotations

import re
import unittest

from helpers import ROOT

from aidd import config
from aidd.docsgen import generate


class GuardCoverageTests(unittest.TestCase):
    def test_the_flag_matches_what_init_wires(self):
        guarded = {k for k, h in config.HARNESSES.items() if h.guard}
        self.assertEqual(guarded, {"claude-code", "codex", "antigravity", "grok-build", "opencode"})
        for key, h in config.HARNESSES.items():
            with self.subTest(harness=key):
                self.assertEqual("guard" in h.wiring, h.guard, "the wiring text says it wires the guard exactly when the flag is on")

    def test_the_pages_name_them_from_the_data(self):
        listed = generate.inline_list("guard-harnesses")
        for rel in ("README.md", "docs/INSTALL.md"):
            with self.subTest(page=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertIn(f"<!-- aidd:gen list:guard-harnesses -->{listed}<!-- aidd:end -->", text)

    def test_no_page_promises_every_agent_a_guard(self):
        overclaim = re.compile(r"gives your coding agent a skill and a guard", re.I)
        for rel in ("README.md", "llms.txt", "docs/INSTALL.md", "docs/QUICKSTART.md", "docs/FAQ.md"):
            with self.subTest(page=rel):
                self.assertIsNone(overclaim.search((ROOT / rel).read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
