"""A Spec freezes a manifest's test section by itself, so a dependency bump never voids the approval, while an edit
of the frozen section after it does; the gate warns when a change edits a test section no Spec freezes."""

import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import git, make_repo

from aidd import workitems
from aidd.kernel import documents
from aidd.workitems import manifest_sections, spec_file

SPEC = """---
aidd_version: "1.0.0"
type: spec
id: S-1
title: Greeting
owner_team: core
change_type: feat
route: normal
confidence: high
open_questions: []
trace_id: s-1
assisted_by: []
rollback: Revert the change.
risk: {summary: "x", dimensions: [], reversible: true}
tasks: [{id: S-1-T1, title: Build, assignee: "agent:developer", scope: [src/], risk: low}]
tests:
  files: [tests/, "pyproject.toml#tool.pytest"]
  commands: [{name: unit, command: [pytest], new_behavior: true, covers: [A1]}]
---

## Intent

Greet.

## Acceptance

- A1: it greets.
"""
BEFORE = '[project]\ndependencies = ["requests==2.32.0"]\n\n[tool.pytest.ini_options]\naddopts = "-q"\n'
BUMPED = BEFORE.replace("2.32.0", "2.32.4")
WEAKER = BEFORE.replace('"-q"', "\"-q -k 'not slow'\"")


def digest(text: str | None, tree: dict | None = None) -> str:
    tree = tree if tree is not None else {"pyproject.toml": "blob-" + str(hash(text)), "tests/test_a.py": "t1"}
    return spec_file.spec_hash(SPEC, tree, lambda p: text if p == "pyproject.toml" else None)


class SectionHashTests(unittest.TestCase):
    def test_only_a_manifest_has_sections_and_a_key_is_dotted(self):
        self.assertIsNone(manifest_sections.section_problem("pyproject.toml#tool.pytest"))
        self.assertIsNone(manifest_sections.section_problem("web/package.json#scripts.test"))
        self.assertIn("only", manifest_sections.section_problem("setup.cfg#tool.pytest") or "")
        self.assertIn("dotted key", manifest_sections.section_problem("pyproject.toml#tool pytest") or "")
        self.assertIsNone(manifest_sections.section_problem("tests/"))
        for bad in (
            "./pyproject.toml#tool.pytest",
            "/pyproject.toml#tool.pytest",
            "a/../pyproject.toml#tool.pytest",
            "a//package.json#jest",
            "a\\package.json#jest",
        ):
            with self.subTest(bad=bad):
                self.assertIn("exact path", manifest_sections.section_problem(bad) or "")


class ManifestSectionsTests(unittest.TestCase):
    def test_the_sections_a_manifest_holds(self):
        self.assertEqual(workitems.test_sections_in("pyproject.toml", BEFORE), ["pyproject.toml#tool.pytest"])
        self.assertEqual(workitems.test_sections_in("app/package.json", '{"jest": {}, "scripts": {"build": "x"}}'), ["app/package.json#jest"])


@unittest.skipUnless(shutil.which("git"), "git is required")
class RealGitTests(unittest.TestCase):
    """The worktree hash and the gate read a frozen section from real git as `aidd approve` does (the batch review's H1, M3)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_repo(Path(tmp.name).resolve() / "repo", "team")
        (self.root / "pyproject.toml").write_text(BEFORE, encoding="utf-8")
        (self.root / "specs").mkdir(exist_ok=True)
        (self.root / "specs" / "S-1.md").write_text(SPEC, encoding="utf-8")
        (self.root / "tests").mkdir(exist_ok=True)
        (self.root / "tests" / "test_a.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "the Spec")

    def test_a_section_its_manifest_does_not_hold_is_named(self):
        from aidd.workitems import spec_warnings

        spec = self.root / "specs" / "S-1.md"
        data, _ = documents.split_front_matter(SPEC.replace("pyproject.toml#tool.pytest", "pyproject.toml#tool.pyest"), "S-1")
        said = spec_warnings.consistency_warnings(spec, data)
        self.assertTrue(any("does not hold, so it freezes nothing" in w for w in said), said)
        data, _ = documents.split_front_matter(SPEC, "S-1")
        self.assertFalse(any("freezes nothing" in w for w in spec_warnings.consistency_warnings(spec, data)))


if __name__ == "__main__":
    unittest.main()
