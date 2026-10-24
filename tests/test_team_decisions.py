"""The team decides what a standard, a project rule, or aidd's default settles, and shows each decision it made: the
handoff note's `decided`, gathered into the digest (both views) and the Merge approval page."""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from helpers import RepoTemplateCase, git
from test_flows import _commit, shop, spec_and_tests

from aidd.tracking import status_rollup
from aidd.workitems import handoff_notes

NOTE = """
```aidd-handoff
done: "the Spec and its tests"
next: verifier
needs: none
stopped_at: none
decided: ["Postgres: the stack's default", "retry 3 times: the SRE standard"]
```

```aidd-handoff
done: "T1"
next: verifier
needs: none
stopped_at: none
decided: "Postgres: the stack's default"
```
"""


class DecidedTests(unittest.TestCase):
    def test_each_decision_once_in_order_and_the_note_still_reads(self):
        self.assertEqual(handoff_notes.team_decisions(NOTE), ["Postgres: the stack's default", "retry 3 times: the SRE standard"])
        self.assertEqual(handoff_notes.handoff_counts(NOTE), (2, 0))  # `decided` breaks no note
        self.assertEqual(handoff_notes.handoff_warnings("specs/SPEC-1.md", NOTE), [])

    def test_none_and_blanks_are_no_decision(self):
        note = "```aidd-handoff\ndone: x\nnext: verifier\nneeds: none\nstopped_at: none\ndecided: none\n```\n"
        self.assertEqual(handoff_notes.team_decisions(note), [])


@unittest.skipUnless(shutil.which("git"), "git is required")
class WhereThePersonReadsThemTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        shop(root)
        spec_and_tests(root)
        spec = Path(root, "specs/SPEC-1.md")
        spec.write_text(spec.read_text(encoding="utf-8") + NOTE, encoding="utf-8")
        _commit(root, "spec: the team's decisions")

    def test_the_digest_lists_them_for_the_team_and_for_the_client(self):
        for client, heading in ((False, "## Decisions the team made"), (True, "## What we decided for you")):
            with self.subTest(client=client):
                d = status_rollup.status_digest(self.root, "main", client=client)
                self.assertIn({"id": "SPEC-1", "decision": "retry 3 times: the SRE standard"}, d["team_decisions"])
                text = status_rollup.digest_markdown(d)
                self.assertIn(heading, text)
                self.assertIn("SPEC-1: Postgres: the stack's default", text)

    def test_the_merge_approval_page_shows_them(self):
        from aidd import platforms
        from aidd.gate import engine
        from aidd.views import merge_approval

        ctx = platforms.build_local_context(repo=str(self.root), run_policy=False)
        page = merge_approval.merge_page(ctx, engine.decide(ctx))
        self.assertIn("Decisions the team made", page)
        self.assertIn("retry 3 times: the SRE standard", page)
        self.assertEqual(git(self.root, "status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
