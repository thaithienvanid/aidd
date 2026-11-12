"""An eval world is checked against today's schemas: with no row of schemas/retired-names.json to find a name from before the first
release, `aidd validate` is what fails a world that holds one (tests/eval_fixture_repos.py runs it on every world)."""

import tempfile
import unittest
from pathlib import Path

from helpers import aidd_here, make_repo

INTENT = "---\ntype: intent\nid: INTENT-1\ntitle: Refund limits\noutcome: Refunds are capped\n{phases}---\n\n## Problem\n\nRefunds are uncapped.\n"


class AWorldWithAnOldIntentShapeFails(unittest.TestCase):
    def validated(self, phases: str) -> str:
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d) / "r", "solo")
            path = root / "product" / "intents" / "INTENT-1.md"
            path.parent.mkdir(parents=True)
            path.write_text(INTENT.format(phases=phases), encoding="utf-8")
            done = aidd_here("validate", "product/intents/INTENT-1.md", cwd=root)
            return f"{done.returncode}\n{done.stdout}{done.stderr}"

    def test_a_slices_list_is_refused_and_phases_pass(self):
        old = self.validated("slices:\n  - {id: SPEC-1, title: Cap}\n")
        self.assertTrue(old.startswith("1\n"), old)
        self.assertIn("slices", old)
        today = self.validated("phases:\n  - {id: P1, name: Cap, specs: [{id: SPEC-1, title: Cap}]}\n")
        self.assertNotIn("slices", today)


if __name__ == "__main__":
    unittest.main()
