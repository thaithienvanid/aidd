"""The work-items page shows an Intent's phases: the Tree and the Intent's own page list each phase by its place, with
its due day or the day it finished, and each slice with its status and its stage, a planned slice too. Shaped like a kit's
plan: a finished phase, a phase in flight with a planned slice, and a phase still to come."""

import datetime as dt
import shutil
import tempfile
import unittest
from pathlib import Path

import page_dom
from helpers import git

from aidd import views, workitems

INTENT = """---
type: intent
id: INTENT-1
title: "Ship the kit"
outcome: "28 cells pass, by 2027-02-19"
phases:
  - id: EPIC-1
    name: "M1: first traced chat"
    due: "2026-11-20"
    finished_on: "2026-11-14"
    specs:
      - {id: SPEC-1, title: Chat from a fresh clone}
  - id: EPIC-2
    name: "M2: four stacks"
    due: "2026-12-04"
    specs:
      - {id: SPEC-2, title: Serve the tools over MCP}
      - {id: SPEC-3, title: Run on LangGraph.js, blocked_by: [SPEC-2]}
  - id: EPIC-3
    name: "M3: tenants kept apart"
    specs:
      - {id: SPEC-4, title: Keep tenants apart}
---
"""


APPROVAL = 'approval: {by: "Dana <dana@example.com>", at: "2026-11-07T21:01:19Z"}\n'


def spec(sid: str, status: str) -> str:
    return (
        f'---\ntype: spec\nparent: INTENT-1\nid: {sid}\ntitle: "{sid} title"\nchange_type: feat\n'
        f"route: normal\nstatus: {status}\ntasks:\n  - {{id: {sid}-T1, title: t, scope: [src/]}}\n---\n"
    )


@unittest.skipUnless(shutil.which("git"), "git is required")
class PhasesOnThePageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "specs").mkdir()
        (root / "product" / "intents").mkdir(parents=True)
        intent = root / "product" / "intents" / "INTENT-1.md"
        intent.write_text(INTENT, encoding="utf-8")
        (root / "specs" / "SPEC-1.md").write_text(spec("SPEC-1", "done"), encoding="utf-8")
        (root / "specs" / "SPEC-2.md").write_text(spec("SPEC-2", "approved"), encoding="utf-8")
        git(root, "init", "-q", "-b", "main")
        git(root, "add", "-A")
        who = ["-c", "user.name=Dana", "-c", "user.email=dana@example.com"]
        git(root, *who, "commit", "-qm", "plan")
        intent.write_text(INTENT.replace("phases:", APPROVAL + "phases:", 1), encoding="utf-8")  # the person's yes, alone in its commit
        git(root, *who, "commit", "-qam", "INTENT-1: approved", "--trailer", "Approved-by: Dana <dana@example.com>", "--trailer", "Approves: INTENT-1")
        answer = workitems.open_work(root, None, include_done=True)
        cls.page = page_dom.parse(views.status_page(answer, title="The open work", written=dt.datetime(2026, 11, 20, 10, 0), project="kit"))

    def phases_in(self, scope: page_dom.Node) -> dict[str, page_dom.Node]:
        return {p.get("data-phase"): p for p in scope.find_all(data_phase=True)}

    def check(self, scope: page_dom.Node) -> None:
        phases = self.phases_in(scope)
        self.assertEqual(list(phases), ["EPIC-1", "EPIC-2", "EPIC-3"])
        heads = [phases[k].find("p").text for k in phases]
        cases = [
            (heads[0], ("Phase 1", "M1: first traced chat", "done", "14 Nov"), ("EPIC-1",)),
            (heads[1], ("Phase 2", "M2: four stacks", "due", "4 Dec"), ("EPIC-2", "done")),
            (heads[2], ("Phase 3", "M3: tenants kept apart"), ("due",)),
        ]
        for head, holds, never in cases:
            with self.subTest(head=head):
                for word in holds:
                    self.assertIn(word, head)
                for word in never:
                    self.assertNotIn(word, head)
        slices = {s.get("data-slice"): s for s in scope.find_all(data_slice=True)}
        self.assertEqual(list(slices), ["SPEC-1", "SPEC-2", "SPEC-3", "SPEC-4"], "every slice shows, with or without a Spec file")
        for sid, status, stage in (("SPEC-2", "approved", "Build"), ("SPEC-3", "planned", "Plan"), ("SPEC-4", "planned", "Plan")):
            with self.subTest(slice=sid):
                self.assertEqual((slices[sid].get("data-slice-status"), slices[sid].get("data-stage")), (status, stage))
                self.assertIn(stage, slices[sid].text)

    def test_the_tree_shows_each_phase_and_its_slices(self):
        self.check(self.page.find("section", data_view="tree"))

    def test_the_intent_page_shows_each_phase_and_its_slices(self):
        self.check(self.page.find("section", data_view="item", data_item="INTENT-1"))

    def test_a_spec_page_names_its_stage(self):
        spec_page = self.page.find("section", data_view="item", data_item="SPEC-2")
        self.assertEqual(spec_page.find(data_field="stage").text, "Build")


if __name__ == "__main__":
    unittest.main()
