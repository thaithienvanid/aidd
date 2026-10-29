"""Test modes and the walking skeleton (V12, V13): under `tests.mode: with_code` the tests are written with the code, so
Spec approval never binds the test files and the builder writes them in its Task; a walking-skeleton Task is the
architect's or the SRE's to build."""

import os
import shutil
import unittest
from pathlib import Path
from unittest import mock

from helpers import RepoTemplateCase, git, make_repo

from aidd import workitems
from aidd.guard import edit_check
from aidd.kernel import documents
from aidd.workitems import decision_records, spec_file

SPEC = "specs/SPEC-230.md"
TEST = "tests/checkout/test_gift_cards.py"


@unittest.skipUnless(shutil.which("git"), "git is required")
class TestModeTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", spec=f"24-tests-written-with-the-code:{SPEC}", approvers=[f"email:{git(root, 'config', 'user.email').strip()}"])

    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "AIDD_SPEC"}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def spec_text(self) -> str:
        return (self.root / SPEC).read_text(encoding="utf-8")

    def write_spec(self, text: str) -> None:
        """The Spec, committed, and a listed Approver's local Spec approval of its hash at that commit."""
        (self.root / SPEC).write_text(text, encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec: SPEC-230")
        head = git(self.root, "rev-parse", "HEAD").strip()
        decision_records.record_local_approval(decision_records.approve_spec_line("SPEC-230", head), str(self.root))

    def decide(self, role, rel):
        return edit_check.check_edit(str(self.root), rel, role)

    def test_under_with_the_builder_writes_the_tests_after_approval(self):
        self.write_spec(self.spec_text())
        for role in ("developer", "verifier", None):
            decision, why = self.decide(role, TEST)
            self.assertEqual(decision, "allow", (role, why))
        self.assertIn("written with the code", self.decide("developer", TEST)[1])
        self.assertEqual(self.decide("developer", "src/other/x.py")[0], "deny")  # its Task's scope still binds

    def test_under_first_the_same_test_is_frozen_once_approved(self):
        self.write_spec(self.spec_text().replace("  mode: with_code\n", ""))
        self.assertEqual(self.decide("developer", TEST)[0], "deny")
        self.assertEqual(self.decide("verifier", TEST)[0], "deny")

    def test_the_hash_leaves_the_test_files_out_only_under_with(self):
        tree = {SPEC: "1" * 40, TEST: "2" * 40}
        changed = dict(tree, **{TEST: "3" * 40})
        text = self.spec_text()
        self.assertEqual(workitems.spec_hash(text, tree), workitems.spec_hash(text, changed))
        first = text.replace("  mode: with_code\n", "")
        self.assertNotEqual(workitems.spec_hash(first, tree), workitems.spec_hash(first, changed))
        self.assertNotEqual(workitems.spec_hash(text, tree), workitems.spec_hash(first, tree))  # switching mode voids an approval

    def test_validate_keeps_with_to_new_code_with_every_item_covered(self):
        def errors(text):
            data, body = documents.split_front_matter(text, SPEC)
            return spec_file.lint_spec(data, body)

        text = self.spec_text()
        self.assertEqual(errors(text), [])
        cases = {
            "risk dimensions": text.replace("  dimensions: []", "  dimensions: [privacy]"),
            "the route is major": text.replace("route: normal", "route: major"),
            "its type is fix": text.replace("type: feat", "type: fix"),
            "no test command covers A2": text.replace("covers: [A1, A2]", "covers: [A1]"),
        }
        for said, changed in cases.items():
            with self.subTest(said=said):
                self.assertTrue(any(said in e for e in errors(changed)), errors(changed))

    def test_a_walking_skeleton_task_is_the_architects_to_build(self):
        text = self.spec_text().replace(
            "    scope: [src/checkout/gift_cards/]\n",
            "    scope: [src/checkout/gift_cards/]\n  - id: TASK-229\n    title: The skeleton\n    scope: [src/app/]\n    skeleton: true\n",
        )
        self.write_spec(text)
        self.assertEqual(self.decide("architect", "src/app/main.py")[0], "allow")
        self.assertEqual(self.decide("architect", "src/checkout/gift_cards/balance.py")[0], "deny")  # a feature slice is not the architect's
        self.assertEqual(self.decide("sre", "src/app/main.py")[0], "allow")

    def test_a_test_another_spec_freezes_stays_frozen(self):
        self.write_spec(self.spec_text())
        other = self.spec_text().replace("id: SPEC-230", "id: SPEC-231").replace("trace_id: spec-230", "trace_id: spec-231").replace("  mode: with_code\n", "")
        other = other.replace("scope: [src/checkout/gift_cards/]", "scope: [src/checkout/vouchers/]")
        (self.root / "specs" / "SPEC-231.md").write_text(other, encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec: SPEC-231")
        head = git(self.root, "rev-parse", "HEAD").strip()
        decision_records.record_local_approval(decision_records.approve_spec_line("SPEC-231", head), str(self.root))
        # SPEC-231 tests first and lists the same file: its approval froze it, whatever SPEC-230's mode.
        self.assertEqual(self.decide("developer", TEST)[0], "deny")


class TestWithGateTests(unittest.TestCase):
    """The gate side of `tests.mode: with_code`, from the conformance case."""

    def context(self):
        from aidd.evals import examples

        return examples.load_example(Path(__file__).resolve().parent.parent / "examples" / "24-tests-written-with-the-code")[0]

    def test_tests_written_with_the_code_count_toward_the_merge_approval_budget(self):
        from aidd import gate

        self.assertEqual(gate.decide(self.context()).record["changed_lines"], 70)  # the test's 30 lines and the code's 40

    def test_a_dimension_the_paths_imply_rules_out_with(self):
        from types import SimpleNamespace

        from aidd.gate.rules import evidence

        said = []
        run = SimpleNamespace(route="normal", implied_dimensions={"privacy"}, add=lambda *a, **k: said.append((a, k)))
        evidence._tests_with(run)
        self.assertEqual(said[0][1]["code"], "tests.with_code_not_allowed")
        self.assertIn("imply the risk dimensions privacy", said[0][0][2])


if __name__ == "__main__":
    unittest.main()
