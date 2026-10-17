"""The Plan step has its own done-check and hands off green, without cutting what the product manager reads or how
deeply it works. Text tests over the real files."""

from __future__ import annotations

import unittest

from helpers import ROOT

from aidd.knowledge import team_registry

TEAM = ROOT / "plugins" / "aidd-team"


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class PlanDoneTests(unittest.TestCase):
    def test_a1_the_loop_says_when_plan_is_done_and_it_is_never_the_suite(self):
        loop = read(".agents/skills/aidd/references/loop.md")
        self.assertIn("Plan runs first only when the work is bigger than one Spec; it is done when `aidd validate` passes on its files", loop)
        done = read("plugins/aidd-team/agents/product-manager.md").split("## Definition of Done", 1)[1].split("## Stop", 1)[0]
        self.assertIn("`aidd validate` on the plan's files, never the test suite", done)

    def test_a2_the_plan_that_merges_holds_no_stub(self):
        self.assertIn("the plan that merges carries the Initiative and the Epics only", read("plugins/aidd-team/agents/product-manager.md"))
        self.assertIn("with the Initiative and the Epics only", read("plugins/aidd-team/commands/plan.md"))

    def test_a3_plan_files_are_written_with_aidd_new_and_edit_never_a_heredoc(self):
        text = read("plugins/aidd-team/agents/product-manager.md")
        self.assertIn("Write them with `aidd new` and Edit, never a heredoc or a compound shell command", text)

    def test_a4_the_product_manager_has_room_for_a_plan_the_size_of_init_1(self):
        self.assertGreaterEqual(team_registry.roles()["roles"]["product-manager"]["max_turns"], 60)

    def test_a5_the_product_manager_reads_everything_it_read_before(self):
        reads = set(team_registry.roles()["roles"]["product-manager"]["reads"])
        self.assertTrue({"request", "config", "production", "postmortem", "retrospective", "feedback", "qualification"} <= reads, reads)


if __name__ == "__main__":
    unittest.main()
