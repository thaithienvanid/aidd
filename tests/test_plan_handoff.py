"""The Plan step has its own done-check and hands off green, without cutting what the product manager reads or how
deeply it works. Text tests over the real files."""

from __future__ import annotations

import unittest

from helpers import ROOT, says

from aidd.knowledge import team_registry

TEAM = ROOT / "plugins" / "aidd-team"


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class PlanDoneTests(unittest.TestCase):
    def test_a1_the_loop_says_when_plan_is_done_and_it_is_never_the_suite(self):
        loop = read(".agents/skills/aidd/references/graph.md")
        self.assertTrue(says(loop, "Plan", "one Spec"), "Plan runs only for work bigger than one Spec")
        self.assertTrue(says(loop, "`aidd validate`", "done"), "Plan is done when aidd validate passes")
        done = read("plugins/aidd-team/agents/product-manager.md").split("## Definition of Done", 1)[1].split("## Stop", 1)[0]
        self.assertTrue(says(done, "`aidd validate`", "never", "test suite"))
        self.assertNotIn("`aidd test`", done)

    def test_a2_the_plan_that_merges_holds_the_intents_and_the_saved_request_alone(self):
        self.assertTrue(says(read("plugins/aidd-team/agents/product-manager.md"), "merges", "Intents", "saved request", "alone"))
        self.assertTrue(says(read("plugins/aidd-team/commands/plan.md"), "merge", "Intents", "saved request", "alone"))

    def test_a3_plan_files_are_written_with_aidd_new_and_edit_never_a_heredoc(self):
        text = read("plugins/aidd-team/agents/product-manager.md")
        self.assertTrue(says(text, "`aidd new`", "Edit", "never a heredoc", "compound shell command"))

    def test_a4_the_product_manager_has_room_for_a_plan_the_size_of_init_1(self):
        self.assertGreaterEqual(team_registry.roles()["roles"]["product-manager"]["max_turns"], 60)

    def test_a5_the_product_manager_reads_everything_it_read_before(self):
        reads = set(team_registry.roles()["roles"]["product-manager"]["reads"])
        self.assertTrue({"request", "config", "production", "postmortem", "retrospective", "feedback", "qualification"} <= reads, reads)


if __name__ == "__main__":
    unittest.main()
