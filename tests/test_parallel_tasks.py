"""Parallel Tasks in worktrees (R195): the lead's rule lives in one reference the team skill links, it names the Claude
Code settings and files the rule rests on, and the developer's agent file stays free of a forced worktree."""

import re
import unittest

from helpers import ROOT

TEAM = ROOT / "plugins" / "aidd-team"
SKILL = TEAM / "skills" / "aidd-team" / "SKILL.md"
FLOWS = TEAM / "skills" / "aidd-team" / "references" / "flows.md"


def text(path) -> str:
    return path.read_text(encoding="utf-8")


def section(heading: str) -> str:
    """The body of a `## heading` in the flows reference, up to the next `##`."""
    return re.split(r"^## ", text(FLOWS).split(f"\n## {heading}\n", 1)[1], maxsplit=1, flags=re.M)[0]


class ParallelTaskRuleTests(unittest.TestCase):
    def test_the_team_skill_points_at_the_section_and_the_section_exists(self):
        self.assertIn("[Parallel Tasks](references/flows.md)", text(SKILL))
        self.assertTrue(section("Parallel Tasks in worktrees").strip())

    def test_the_reference_names_what_claude_code_reads(self):
        """Each name is Claude Code's own (worktree docs, checked 2026-11-04), so a misspelling breaks the advice."""
        body = section("Parallel Tasks in worktrees")
        for name in (
            'isolation: "worktree"',
            "worktree",
            "baseRef",
            '"head"',
            ".worktreeinclude",
            "git worktree remove",
            "git merge-base --is-ancestor",
            "git.branch.delete",
        ):
            with self.subTest(name=name):
                self.assertIn(name, body)

    def test_each_step_has_its_own_numbered_item(self):
        items = re.findall(r"^(\d)\. \*\*([^*]+)\*\*", section("Parallel Tasks in worktrees"), re.M)
        self.assertEqual([n for n, _ in items], ["1", "2", "3", "4"])
        self.assertTrue(any("Cleanup" in title for _, title in items), "cleanup is a step of its own, never a side effect")

    def test_the_cleanup_asks_for_the_branch_delete_before_removing(self):
        self.assertIn('"git.branch.delete"', text(ROOT / "schemas" / "risks.json"), "the action the reference asks about exists")

    def test_the_developer_file_does_not_force_a_worktree(self):
        """A lone fast-lane developer builds on the change's branch; only the lead's per-Task call isolates."""
        self.assertNotIn("isolation:", text(TEAM / "agents" / "developer.md").split("---")[1])
        self.assertIn('isolation: "worktree"', text(TEAM / "commands" / "implement.md"))


if __name__ == "__main__":
    unittest.main()
