"""A project's own templates: `aidd new <type>` starts from `<docs.dir>/templates/<type>.md` when it exists, else from the
skill's asset, and `aidd validate` checks the result as it checks any other, so a template may add sections but never
drop a required one. A template that leads outside that folder is refused, and nothing is written."""

from __future__ import annotations

import contextlib
import datetime as dt
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import helpers
from aidd import config, workitems
from aidd.kernel import resources
from aidd.workitems import authoring

TODAY = dt.date(2026, 11, 6)


def asset(name: str) -> str:
    return (resources.data_dir("skill") / "assets" / name).read_text(encoding="utf-8")


class AProjectTemplate(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = helpers.make_repo(Path(tmp.name) / "repo", "solo")
        self.templates = self.root / "docs" / "templates"
        self.templates.mkdir(parents=True)

    def spec(self, id_: str = "SPEC-1") -> Path:
        return workitems.new_object(self.root, workitems.NewObject(item_type="spec", id=id_, title="A discount", today=TODAY))

    def test_aidd_new_starts_from_the_projects_template_first(self):
        (self.templates / "spec-short.md").write_text(asset("spec-short.md") + "\n## Our release checklist\n\n- [ ] the docs\n")
        text = self.spec().read_text()
        self.assertIn("## Our release checklist", text)
        self.assertIn("\nid: SPEC-1\n", text)  # the placeholders fill as in aidd's own
        # Each other `aidd new` type reads its own name there; a type without one keeps aidd's template.
        (self.templates / "adr.md").write_text("# ADR {{number}}: {{title}}\n\nOur own shape, for {{spec}}.\n")
        (self.templates / "glossary.md").write_text("# Our glossary\n")
        (self.templates / "exploration.md").write_text(asset("exploration.md").replace("## ", "## Ours: ", 1))
        adr, _ = workitems.new_doc(self.root, workitems.NewDoc(doc_type="adr", topic="Pick a queue", spec_id="SPEC-1", today=TODAY))
        self.assertEqual(adr.read_text(), "# ADR 0001: Pick a queue\n\nOur own shape, for SPEC-1.\n")
        (glossary,) = workitems.new_repo_doc(self.root, doc_type="glossary", today=TODAY)
        self.assertEqual(glossary.read_text(), "# Our glossary\n")
        with contextlib.chdir(self.root):
            explored = workitems.new_exploration(Path("specs/SPEC-1/explore/queue"), question="Which queue?", today=TODAY)
            self.assertIn("## Ours: ", explored.read_text())
        threat, _ = workitems.new_doc(self.root, workitems.NewDoc(doc_type="threat-model", topic="Checkout", spec_id="SPEC-1", today=TODAY))
        self.assertIn(asset("threat-model.md").splitlines()[0].split("{{")[0], threat.read_text())

    def test_the_folder_follows_docs_dir_and_git_keeps_it(self):
        """Templates are a team's shared shape, so they live where git keeps files: never in a folder of `.aidd/`."""
        path = self.root / ".aidd" / "config.yaml"
        path.write_text(path.read_text().rstrip("\n") + "\ndocs:\n  dir: handbook\n")
        self.assertEqual(authoring.templates_dir(self.root), "handbook/templates")
        (self.root / "handbook" / "templates").mkdir(parents=True)
        (self.root / "handbook" / "templates" / "glossary.md").write_text("# Ours\n")
        (glossary,) = workitems.new_repo_doc(self.root, doc_type="glossary", docs_dir="handbook", today=TODAY)
        self.assertEqual(glossary.read_text(), "# Ours\n")
        (self.root / ".gitignore").write_text(config.OUTPUT_IGNORE + "\n")
        ignored = subprocess.run(["git", "check-ignore", "-q", "handbook/templates/glossary.md"], cwd=self.root, check=False)
        self.assertEqual(ignored.returncode, 1)  # 1: not ignored

    def test_aidd_validate_still_requires_what_the_template_drops(self):
        cases = [
            # (what the project's template does, an error or warning `aidd validate` gives for the Spec it writes)
            ("drops rollback", asset("spec-short.md").replace("rollback: Revert the change.", ""), "rollback"),
            ("drops the Request section", asset("spec-short.md").replace("## Request", "## Background"), "no '## Request' section"),
        ]
        for i, (what, template, finding) in enumerate(cases, start=2):
            with self.subTest(template=what):
                (self.templates / "spec-short.md").write_text(template)
                with contextlib.chdir(self.root):
                    code, out = helpers.run_cli("validate", self.spec(f"SPEC-{i}").relative_to(self.root).as_posix())
                self.assertIn(finding, out)
        (self.templates / "spec-short.md").unlink()
        with contextlib.chdir(self.root):
            code, out = helpers.run_cli("validate", self.spec("SPEC-9").relative_to(self.root).as_posix())
        self.assertNotIn("rollback", out)
        self.assertNotIn("no '## Request' section", out)

    def test_a_template_that_leads_outside_the_folder_is_refused(self):
        outside = self.root.parent / "elsewhere"
        outside.mkdir()
        (outside / "spec-short.md").write_text("---\ntype: spec\n---\nnot the project's\n")
        os.symlink(outside / "spec-short.md", self.templates / "spec-short.md")
        with self.assertRaisesRegex(ValueError, r"docs/templates/spec-short\.md leads outside"):
            self.spec()
        self.assertFalse((self.root / "specs" / "SPEC-1.md").exists())
        # The folder itself a symlink out of the repository: refused too.
        (self.templates / "spec-short.md").unlink()
        self.templates.rmdir()
        os.symlink(outside, self.templates)
        with self.assertRaisesRegex(ValueError, "leads outside"):
            self.spec()
        self.assertFalse((self.root / "specs" / "SPEC-1.md").exists())

    def test_a_template_name_is_a_plain_type(self):
        for name in ("../spec", "spec/../../x", "Spec", ""):
            with self.subTest(name=name), self.assertRaises(ValueError):
                authoring.template_text(self.root, name, "spec.md")


if __name__ == "__main__":
    unittest.main()
