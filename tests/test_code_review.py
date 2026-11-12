"""Claude Code Review reads REVIEW.md: its sections, the skill include `aidd init --aidd-team` adds, and the Merge step."""

import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd.kernel import resources
from aidd.setup import adoption, uninstalling

TEMPLATE = resources.data_dir("templates") / "REVIEW.md"
LOOP = ROOT / ".agents" / "skills" / "aidd" / "references" / "loop.md"


def init(root: Path, **kw) -> list[str]:
    opts = adoption.InitOptions(profile="solo", ci="none", links=[], skill=False, harnesses=[], approvers=["@me"], **kw)
    return adoption.init(root, opts)


def include_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.startswith("@")]


class TemplateTests(unittest.TestCase):
    def test_sections_a_managed_review_reads(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        for heading in ("### What Important means here", "## Nits", "## Out of scope: do not report"):
            self.assertIn(heading, text)
        important = text.split("### What Important means here", 1)[1].split("\n#", 1)[0]
        self.assertIn("Critical or High", important)
        self.assertIn("still approves", important)
        self.assertIn("at most 5 nits", text.split("## Nits", 1)[1])

    def test_no_include_line_without_the_team(self):
        self.assertEqual(include_lines(TEMPLATE.read_text(encoding="utf-8")), [])


class InitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.policy = self.root / "REVIEW.md"
        self.skill = self.root / adoption.REVIEW_SKILL_FILE

    def tearDown(self):
        self.tmp.cleanup()

    def install_skill(self):
        self.skill.parent.mkdir(parents=True)
        self.skill.write_text("---\nname: aidd-code-review\n---\n", encoding="utf-8")

    def test_the_include_names_a_skill_file_that_exists(self):
        self.install_skill()
        init(self.root)
        adoption.include_review_skill(self.root, [])
        lines = include_lines(self.policy.read_text(encoding="utf-8"))
        self.assertEqual(lines, [f"@{adoption.REVIEW_SKILL_FILE}"])
        self.assertTrue((self.root / lines[0][1:]).is_file())

    def test_init_without_the_team_has_no_include(self):
        init(self.root)
        self.assertEqual(self.policy.read_text(encoding="utf-8"), TEMPLATE.read_text(encoding="utf-8"))

    def test_no_include_without_the_skill_file(self):
        init(self.root)
        adoption.include_review_skill(self.root, [])
        self.assertEqual(include_lines(self.policy.read_text(encoding="utf-8")), [])

    def test_a_policy_a_person_changed_is_left_alone(self):
        init(self.root)
        self.policy.write_text("# Ours\n", encoding="utf-8")
        self.install_skill()
        adoption.include_review_skill(self.root, [])
        self.assertEqual(self.policy.read_text(encoding="utf-8"), "# Ours\n")

    def test_it_is_added_once(self):
        init(self.root)
        self.install_skill()
        for _ in range(2):
            adoption.include_review_skill(self.root, [])
        self.assertEqual(len(include_lines(self.policy.read_text(encoding="utf-8"))), 1)

    def test_uninstall_removes_the_policy_with_the_include(self):
        init(self.root)
        self.install_skill()
        adoption.include_review_skill(self.root, [])
        uninstalling.uninstall(self.root, yes=True)
        self.assertFalse(self.policy.exists())


class MergeStepTests(unittest.TestCase):
    def test_merge_reads_the_managed_reviews_important_findings_and_does_not_decide(self):
        merge = LOOP.read_text(encoding="utf-8").split("## 4. Merge", 1)[1].split("\n## ", 1)[0]
        self.assertIn("Important", merge)
        self.assertIn("never the Merge approval", merge)


if __name__ == "__main__":
    unittest.main()
