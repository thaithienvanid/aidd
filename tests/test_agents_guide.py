"""The project's AGENTS.md is one of the team's living documents: `aidd new agents` writes the guide from its template
above aidd's own section, the architect owns it, and a change that makes a line untrue updates it."""

from __future__ import annotations

import shutil
import unittest

from helpers import RepoTemplateCase
from test_flows import shop

from aidd.knowledge import team_registry
from aidd.workitems import authoring


@unittest.skipUnless(shutil.which("git"), "git is required")
class ProjectGuideTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        shop(root)

    def test_the_guide_goes_above_aidds_own_section(self):
        before = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        authoring.new_repo_doc(self.root, kind="agents")
        text = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Agents\n\n<!-- The project's guide"))
        self.assertLess(text.index("## Build, test, and run"), text.index(authoring.SECTION_MARK))
        self.assertTrue(text.endswith(before[before.index(authoring.SECTION_MARK) :]))  # aidd's section, unchanged
        with self.assertRaises(FileExistsError):  # the project has one guide: change it in its own change
            authoring.new_repo_doc(self.root, kind="agents")

    def test_with_no_agents_md_it_writes_the_guide_alone(self):
        (self.root / "AGENTS.md").unlink()
        authoring.new_repo_doc(self.root, kind="agents")
        self.assertIn("## Rules", (self.root / "AGENTS.md").read_text(encoding="utf-8"))

    def test_the_architect_owns_it_and_it_is_living(self):
        doc = team_registry.roles()["loop"]["documents"]["agents"]
        self.assertEqual((doc["owner"], doc["lifecycle"]), ("architect", "living"))
        self.assertIn("AGENTS.md", team_registry.roles()["roles"]["architect"]["writes"])


if __name__ == "__main__":
    unittest.main()
