"""`aidd delegate check` on the merge of an approved Spec's change: it defers when the change moves what the approval
froze, the Spec's tests, its scope, or the Spec's own path. Split from test_delegation_spec to keep each file inside the
test budget."""

import tempfile
from pathlib import Path

from test_delegation_check import codes
from test_delegation_spec import SpecCase


class ChangedAfterApprovalTests(SpecCase):
    def test_tests_changed_after_approval_defer_the_merge(self):
        loosened = "import unittest\n\nclass T(unittest.TestCase):\n    def test_discount(self):\n        pass\n"
        cases = {
            "a test loosened": {"tests/test_discount.py": loosened},
            "a test renamed away and its copy loosened": {"tests/test_discount.py": None, "tests/test_discount_v2.py": loosened},
        }
        for name, tests in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                self.root = Path(d).resolve()
                repo, spec_head = self.spec_repo()
                self.person_approved(spec_head)
                head = self.built(repo, tests)
                self.assertEqual(codes(repo.check(head)), ["tests-changed"])
        with tempfile.TemporaryDirectory() as d:
            self.root = Path(d).resolve()
            repo, spec_head = self.spec_repo()
            self.person_approved(spec_head)
            self.assertEqual(codes(repo.check(self.built(repo, {}))), [], "a recorded yes and unchanged tests pass")

    def test_a_change_outside_the_approved_scope_or_spec_defers(self):
        repo, spec_head = self.spec_repo()
        self.person_approved(spec_head)
        self.assertEqual(codes(repo.check(self.built(repo, {"src/billing/rates.py": "RATE = 1\n"}))), ["out-of-scope"])
        with tempfile.TemporaryDirectory() as d:
            self.root = Path(d).resolve()
            repo, spec_head = self.spec_repo()
            self.person_approved(spec_head)
            text = (self.root / "specs/SPEC-220.md").read_text(encoding="utf-8")
            repo.write("specs/SPEC-220.md", text.replace("new_behavior: true", "new_behavior: true\n      retries: 3"))
            self.assertEqual(codes(repo.check(self.built(repo, {}))), ["tests-changed"], "a changed tests block is spec.revise")

    def test_a_spec_moved_after_its_approval_defers(self):
        repo, spec_head = self.spec_repo()
        self.person_approved(spec_head)
        text = (self.root / "specs/SPEC-220.md").read_text(encoding="utf-8")
        (self.root / "specs/SPEC-220.md").unlink()
        repo.write("specs/done/SPEC-220.md", text)
        self.assertEqual(codes(repo.check(self.built(repo, {}, spec="specs/done/SPEC-220.md"))), ["tests-changed"])


if __name__ == "__main__":
    import unittest

    unittest.main()
