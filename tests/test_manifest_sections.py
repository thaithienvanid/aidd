"""A Spec freezes a manifest's test section by itself, so a dependency bump never voids the approval, while an edit
of the frozen section after it does; the gate warns when a change edits a test section no Spec freezes."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import git, make_repo

from aidd import workitems
from aidd.gate import inputs
from aidd.kernel import documents
from aidd.kernel import git as gitutil
from aidd.workitems import derived_status, manifest_sections, spec_file

SPEC = """---
aidd_version: "1.0.0"
kind: spec
id: S-1
title: Greeting
owner_team: core
type: feat
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
    def test_a_dependency_bump_keeps_the_approval_and_a_weaker_test_setting_voids_it(self):
        self.assertEqual(digest(BEFORE), digest(BUMPED), "the rest of the file stays free")
        self.assertNotEqual(digest(BEFORE), digest(WEAKER), "the frozen section voids the approval")

    def test_with_no_reader_or_a_broken_manifest_the_whole_file_counts(self):
        tree = {"pyproject.toml": "b1", "tests/test_a.py": "t1"}
        bumped = {"pyproject.toml": "b2", "tests/test_a.py": "t1"}
        self.assertNotEqual(spec_file.spec_hash(SPEC, tree), spec_file.spec_hash(SPEC, bumped), "no reader: the blob")
        broken = "[tool.pytest\n"
        self.assertNotEqual(digest(broken, tree), digest(broken, bumped), "unparsable: the blob")

    def test_a_spec_with_no_section_hashes_as_before(self):
        plain = SPEC.replace(', "pyproject.toml#tool.pytest"', "")
        tree = {"tests/test_a.py": "t1", "pyproject.toml": "b1"}
        self.assertEqual(spec_file.spec_hash(plain, tree), spec_file.spec_hash(plain, tree, lambda p: "anything"))

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


class SectionsChangedTests(unittest.TestCase):
    def test_what_changed_and_an_unreadable_manifest(self):
        self.assertEqual(workitems.sections_changed("pyproject.toml", BEFORE, BUMPED), [])
        self.assertEqual(workitems.sections_changed("pyproject.toml", BEFORE, WEAKER), ["tool.pytest"])
        self.assertEqual(workitems.sections_changed("pyproject.toml", None, BEFORE), ["tool.pytest"], "a new manifest with tests")
        self.assertEqual(workitems.sections_changed("pyproject.toml", BEFORE, "[["), list(manifest_sections.TEST_SECTIONS["pyproject.toml"]))
        before = '{"scripts": {"test": "vitest run"}, "dependencies": {"a": "1"}}'
        self.assertEqual(workitems.sections_changed("package.json", before, before.replace('"1"', '"2"')), [])
        self.assertEqual(workitems.sections_changed("package.json", before, before.replace("vitest run", "true")), ["scripts.test"])

    def test_scripts_test_freezes_every_script_npm_test_runs(self):
        """npm runs pretest and posttest around test, and a script runs others by name: each one is frozen with it."""
        base = {
            "pretest": "npm run lint",
            "test": "npm run unit && yarn e2e",
            "posttest": "c8 report",
            "lint": "eslint .",
            "unit": "vitest run",
            "e2e": "playwright test",
            "build": "vite build",
        }

        def changed(**edits):
            after = dict(base, **edits)
            return workitems.sections_changed("package.json", json.dumps({"scripts": base}), json.dumps({"scripts": after}))

        for name in ("pretest", "posttest", "lint", "unit", "e2e", "build"):
            with self.subTest(script=name):
                self.assertEqual(changed(**{name: "true"}), ["scripts.test"], "a test that calls a runner freezes every script")
        alone = {"test": "vitest run", "build": "vite build"}
        before, after = json.dumps({"scripts": alone}), json.dumps({"scripts": dict(alone, build="vite build --mode prod")})
        self.assertEqual(workitems.sections_changed("package.json", before, after), [], "a self-contained test leaves the rest free")
        self.assertEqual(workitems.sections_changed("package.json", before, before.replace("vitest run", "true")), ["scripts.test"])
        for test in ("vitest run && echo ok", "$npm_execpath run unit", "deno task test", "node --run unit", "run-s unit"):
            with self.subTest(test=test):
                weird = json.dumps({"scripts": {"test": test, "build": "vite build"}})
                bumped = json.dumps({"scripts": {"test": test, "build": "vite build --mode prod"}})
                self.assertEqual(workitems.sections_changed("package.json", weird, bumped), ["scripts.test"], "not plainly self-contained: every script")

    def test_a_runner_config_read_before_a_manifest_is_the_harness(self):
        """pytest 9 reads pytest.toml before pyproject.toml, coverage .coveragerc, and so on: each can override a frozen
        section, so each counts as the harness."""
        from aidd.gate.rules import route

        paths = ["pytest.toml", ".pytest.ini", "pkg/.coveragerc", "web/vite.config.ts", ".nycrc.json", ".c8rc", ".npmrc", "ava.config.js"]
        self.assertEqual(route.test_harness_paths(paths, []), paths)

    def test_a_pytest_plugin_and_with_code_stay_frozen(self):
        plugin = '[project.entry-points.pytest11]\nmine = "pkg.plugin"\n'
        self.assertEqual(workitems.sections_changed("pyproject.toml", plugin, plugin.replace("pkg.plugin", "pkg.other")), ["project.entry-points.pytest11"])
        spec = {"tests": {"mode": "with_code", "files": ["tests/", "pyproject.toml#tool.pytest"]}}
        self.assertEqual(spec_file.frozen_paths(spec), ["pyproject.toml#tool.pytest"], "the harness, not a test written with the code")

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

    def test_the_worktree_hash_is_the_hash_aidd_approve_records(self):
        head = git(self.root, "rev-parse", "HEAD").strip()
        approved = spec_file.spec_hash(SPEC, gitutil.ls_tree(head, str(self.root)), lambda p: gitutil.show(head, p, str(self.root)))
        observer = derived_status.Observer(self.root, None)
        data, _ = documents.split_front_matter(SPEC, "S-1")
        self.assertEqual(observer.hash_worktree(SPEC, data), approved)
        (self.root / "pyproject.toml").write_text(BUMPED, encoding="utf-8")
        self.assertEqual(derived_status.Observer(self.root, None).hash_worktree(SPEC, data), approved, "a dependency bump")
        (self.root / "pyproject.toml").write_text(WEAKER, encoding="utf-8")
        self.assertNotEqual(derived_status.Observer(self.root, None).hash_worktree(SPEC, data), approved, "the frozen section")

    def test_a_section_its_manifest_does_not_hold_is_named(self):
        from aidd.workitems import spec_warnings

        spec = self.root / "specs" / "S-1.md"
        data, _ = documents.split_front_matter(SPEC.replace("pyproject.toml#tool.pytest", "pyproject.toml#tool.pyest"), "S-1")
        said = spec_warnings.consistency_warnings(spec, data)
        self.assertTrue(any("does not hold, so it freezes nothing" in w for w in said), said)
        data, _ = documents.split_front_matter(SPEC, "S-1")
        self.assertFalse(any("freezes nothing" in w for w in spec_warnings.consistency_warnings(spec, data)))

    def test_the_gate_context_carries_the_manifest_at_head_and_where_the_branch_left_the_base(self):
        base = git(self.root, "rev-parse", "HEAD").strip()
        git(self.root, "switch", "-qc", "change")
        (self.root / "pyproject.toml").write_text(WEAKER, encoding="utf-8")
        git(self.root, "commit", "-qam", "weaker")
        head = git(self.root, "rev-parse", "HEAD").strip()
        decl = inputs.declared_inputs(str(self.root), base, head, "")
        self.assertEqual(decl["head_files"].get("pyproject.toml"), WEAKER)
        self.assertEqual(decl["base_files"].get("pyproject.toml"), BEFORE)


if __name__ == "__main__":
    unittest.main()
