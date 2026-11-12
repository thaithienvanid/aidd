"""The living documents in `loop.documents` (schemas/roles.json): each has one owner and the home `aidd new` writes, and
a Spec's tracking plan, SLO doc, or compliance record feeds the product-level document it folds into, so the
same-change check (`living_work`) warns when a change leaves that document as it was."""

import os
import re
import shutil
import unittest
from pathlib import Path

from helpers import RepoTemplateCase, git, make_repo, run_cli

from aidd import knowledge
from aidd.kernel import globs
from aidd.workitems import living_work


@unittest.skipUnless(shutil.which("git"), "git is required")
class FoldTests(RepoTemplateCase):
    """`loop.documents` in schemas/roles.json says what each document folds into, and the same-change check reads it."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", branch=None)

    def setUp(self):
        super().setUp()
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        os.chdir(self.root)

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    FOLDS = {
        # the Spec's document -> (how the product-level one starts, the file it keeps, the Spec document that feeds it)
        "tracking-plan": (("new", "metrics-dictionary"), "docs/product/metrics.md", "specs/SPEC-90/tracking-plan-cart.md"),
        "slo": (("new", "service-card", "payments"), "docs/services/payments.md", "specs/SPEC-90/slo-payments.md"),
        "compliance-record": (("new", "control-register"), "docs/compliance/control-register.md", "specs/SPEC-90/compliance-record-gdpr.md"),
    }

    def test_each_living_document_has_one_owner_and_the_home_aidd_new_writes(self):
        documents = knowledge.roles()["loop"]["documents"]
        homes = {
            "product-brief": "docs/product/brief.md",
            "metrics-dictionary": "docs/product/metrics.md",
            "control-register": "docs/compliance/control-register.md",
            "improvement-log": "docs/retros/improvement-log.md",
            "service-card": "docs/services/payments.md",
        }
        for doc_type, rel in homes.items():
            with self.subTest(doc_type=doc_type):
                files = [f.replace("{docs}", "docs") for f in documents[doc_type]["files"]]
                self.assertTrue(globs.match_any(files, rel), files)
                self.assertEqual((documents[doc_type]["lifecycle"], documents[doc_type]["belongs_to"]), ("living", "product"))

    def test_a_spec_document_feeds_its_product_document(self):
        documents = knowledge.roles()["loop"]["documents"]
        for doc_type, (target, _, _) in self.FOLDS.items():
            self.assertEqual(documents[doc_type]["feeds"], target[1], doc_type)

    def test_changing_the_spec_document_alone_warns_and_folding_it_in_does_not(self):
        for doc_type, (command, product, feeder) in self.FOLDS.items():
            with self.subTest(doc_type=doc_type):
                git(self.root, "switch", "-q", "main")
                self.assertEqual(run_cli(*command)[0], 0)
                git(self.root, "add", "-A")
                git(self.root, "commit", "-qm", f"the {command[1]}")
                git(self.root, "switch", "-qc", f"spec/{doc_type}")
                self.write(feeder, "# a change\n")
                path, data = self.root / "specs/SPEC-90.md", {"type": "spec", "id": "SPEC-90", "route": "normal"}
                (found,) = living_work.same_change_warnings(path, data, self.root)
                self.assertIn(command[1], found)
                self.write(product, (self.root / product).read_text(encoding="utf-8") + "\n| a new row |\n")
                self.assertEqual(living_work.same_change_warnings(path, data, self.root), [])
                git(self.root, "checkout", "-qf", "main")
                git(self.root, "clean", "-qfd")


@unittest.skipUnless(shutil.which("git"), "git is required")
class UnplannedChangeTests(RepoTemplateCase):
    """Spec Kit's `converge` names unrequested work; aidd warns of each file an approved Spec's change alters that its
    plan never names, so work outside every Task's scope shows before review."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", branch=None)

    DATA = {
        "type": "spec",
        "id": "SPEC-91",
        "route": "normal",
        "status": "approved",
        "tasks": [{"id": "T1", "scope": ["src/refunds/**"]}],
        "tests": {"files": ["tests/test_refunds.py", "pyproject.toml#tool.pytest"]},
        "docs": [{"type": "adr", "path": "docs/decisions/0007-refunds.md"}],
    }

    def write(self, rel: str, text: str = "x\n") -> None:
        (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.root / rel).write_text(text, encoding="utf-8")

    def test_a_file_no_task_test_or_doc_names_warns_once_and_only_while_the_spec_is_open(self):
        path = self.root / "specs/SPEC-91.md"
        self.write("notes.txt")
        self.assertEqual(living_work.unplanned_change_warnings(path, self.DATA, self.root), [])  # main: no Spec changed
        git(self.root, "switch", "-qc", "spec/refunds")
        for rel in (
            "src/refunds/api.py",
            "tests/test_refunds.py",
            "pyproject.toml",
            "docs/decisions/0007-refunds.md",
            "specs/SPEC-91/tech-spec-api.md",
            "CHANGELOG.md",
            "src/billing/tax.py",
        ):
            self.write(rel)
        self.write("specs/SPEC-91.md", "---\ntype: spec\nid: SPEC-91\n---\n")
        found = living_work.unplanned_change_warnings(path, self.DATA, self.root)
        self.assertEqual([re.search(r": (\S+) changed, but", f).group(1) for f in found], ["notes.txt", "src/billing/tax.py"])
        self.assertIn("spec.revise", found[0])
        for status in ("draft", "ready", "done"):
            with self.subTest(status=status):
                self.assertEqual(living_work.unplanned_change_warnings(path, {**self.DATA, "status": status}, self.root), [])
        # Two Specs on one branch: a file no changed Spec's plan names still warns, and one the other Spec's plan names does not.
        self.write("specs/SPEC-92.md", "---\ntype: spec\nid: SPEC-92\n---\n")
        found = living_work.unplanned_change_warnings(path, self.DATA, self.root)
        self.assertEqual([re.search(r": (\S+) changed, but", f).group(1) for f in found], ["notes.txt", "src/billing/tax.py"])
        self.write("specs/SPEC-92.md", "---\ntype: spec\nid: SPEC-92\ntasks:\n  - id: T1\n    scope: [src/billing/**]\n---\n")
        found = living_work.unplanned_change_warnings(path, self.DATA, self.root)
        self.assertEqual([re.search(r": (\S+) changed, but", f).group(1) for f in found], ["notes.txt"])


if __name__ == "__main__":
    unittest.main()
