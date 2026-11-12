"""`aidd delegate check` on the merge of a Spec approved before `aidd upgrade`, whole, not one function. Split from
test_delegation_upgrade to keep each file inside the test budget."""

import tempfile
import unittest
from pathlib import Path

from test_delegation_check import codes
from test_delegation_spec import SpecCase
from test_delegation_upgrade import old_spec

from aidd.delegation import local_run
from aidd.setup import migrating

# Old names in the config on the default branch: a cut (`project.repo`) and a rename (`mcp.approve_own_tools`).
OLD_CONFIG = "project:\n  repo: https://example.com/x.git\nmcp:\n  approve_own_tools: true\n"


class UpgradeEndToEndTests(SpecCase):
    """The full merge check, not one function. Invariant: a pure migration never changes what a check decides. The Spec was
    approved while its file, and in one case the config, were in an earlier shape, and the head only carries `aidd upgrade`'s
    writes beside its implementation."""

    def merged_after_upgrade(self, where: str, tests: dict | None = None) -> dict:
        """`where` is what is in the earlier shape besides the Spec: `spec` (nothing), or `tip` (the default branch's config, and so
        the branch's too, which the upgrade then moves: a config is a reserved path)."""
        repo, spec_head = self.spec_repo(spec_text=old_spec(), **({"extra": OLD_CONFIG} if where == "tip" else {}))
        self.delegate_approved(spec_head)
        found = migrating.plan(self.root)
        migrating.apply(self.root, found)
        self.assertIn("specs/SPEC-220.md", found.texts, "the upgrade moved the Spec")
        return repo.check(self.built(repo, tests or {}))

    def test_a_spec_approved_before_the_upgrade_still_passes_after_it(self):
        for where in ("spec",):
            with self.subTest(where), tempfile.TemporaryDirectory() as d:
                self.root = Path(d).resolve()
                result = self.merged_after_upgrade(where)
                self.assertEqual((result["outcome"], codes(result)), ("eligible", []), result["reasons"])

    def test_a_config_on_the_default_branch_in_the_earlier_shape_is_read_not_refused(self):
        """The head here changes the config, a reserved path, so the merge is a person's. It defers for that, and never because
        the default branch's config does not load."""
        with tempfile.TemporaryDirectory() as d:
            self.root = Path(d).resolve()
            found = codes(self.merged_after_upgrade("tip"))
            self.assertNotIn("config_unreadable", found)
            self.assertIn("reserved_path", found)

    def test_the_approvals_tests_run_again_on_a_tree_in_the_earlier_shape(self):
        """The re-run of the Spec's tests at the approval commit reads that commit's config and Spec in today's shape. The head is
        read as it is, so the same run with no `old_shape` stops at the earlier shape's names, naming the step."""
        _, spec_head = self.spec_repo(spec_text=old_spec(), extra=OLD_CONFIG)
        evidence, why = local_run.run_on_head(str(self.root), spec_head, "main", "specs/SPEC-220.md", old_shape=True)
        self.assertEqual(why, "")
        self.assertEqual(local_run.red_problem(evidence, why), "", "the new test fails on the base for a real reason")
        evidence, why = local_run.run_on_head(str(self.root), spec_head, "main", "specs/SPEC-220.md")
        self.assertIsNone(evidence)
        self.assertIn("aidd upgrade --yes", why)

    def test_an_approval_whose_config_does_not_load_even_in_todays_shape_stops_with_the_step(self):
        _, spec_head = self.spec_repo(spec_text=old_spec(), extra="not_a_setting: 1\n")
        evidence, why = local_run.run_on_head(str(self.root), spec_head, "main", "specs/SPEC-220.md", old_shape=True)
        self.assertIsNone(evidence)
        self.assertIn("approve the Spec again", why)

    def test_a_real_change_beside_the_upgrade_still_defers(self):
        """The frozen test file is still compared by its bytes (a changed `tests` block is the first test's table)."""
        with tempfile.TemporaryDirectory() as d:
            self.root = Path(d).resolve()
            self.assertEqual(codes(self.merged_after_upgrade("spec", {"tests/test_discount.py": "import unittest\n"})), ["tests_changed"])


if __name__ == "__main__":
    unittest.main()
