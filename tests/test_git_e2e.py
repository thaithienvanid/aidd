"""End to end in a throwaway git repository: init, doctor, `aidd test` (green and red), a local gate."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, git  # noqa: F401  (ROOT puts src on sys.path)

from aidd.setup import doctor_checks
from aidd.setup import adoption
from aidd import config
from aidd.platforms import local_context
from aidd.gate import rulebook, test_runner
from aidd.kernel import git as gitutil
from aidd.gate import decide

CONFIG = """aidd_version: "1.0.0"
profile: team

owners:
  approvers: [bob]
  specialists:
    security: ["@sec"]

tests:
  - name: unit
    command: ["{py}", -c, print('suite ok')]
"""

SPEC = """---
aidd_version: "1.0.0"
kind: spec
id: SPEC-1
title: Greeting says hello
owner_team: core
type: feat
route: normal
confidence: high
open_questions: []
trace_id: spec-1
assisted_by: []
rollback: Revert the PR.

risk:
  summary: Adds a greeting function.
  dimensions: []
  reversible: true

tasks:
  - id: T1
    title: Implement greet
    scope: [app/]

tests:
  files: [checks/test_greet.py]

  commands:
    - name: greet
      command: ["{py}", checks/test_greet.py]
      new_behavior: true
---

## Context

Tiny example.

## Acceptance

Invariant: greet() returns "hello".
"""

TEST = "import sys\nsys.path.insert(0, '.')\nfrom app.greet import greet\nassert greet() == 'hello'\nprint('ok')\n"


@unittest.skipUnless(shutil.which("git"), "git is required")
class GitEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "alice@example.com")
        git(self.root, "config", "user.name", "Alice")
        git(self.root, "config", "commit.gpgsign", "false")
        (self.root / ".aidd").mkdir()
        (self.root / ".aidd/config.yaml").write_text(CONFIG.format(py=sys.executable.replace("\\", "/")), encoding="utf-8")
        (self.root / "app").mkdir()
        (self.root / "app/__init__.py").write_text("", encoding="utf-8")
        # What a test run leaves behind, ignored as a Python project ignores it: a tree with it stays clean.
        (self.root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "base")
        git(self.root, "checkout", "-qb", "feature")
        (self.root / "specs").mkdir()
        (self.root / "specs/SPEC-1.md").write_text(SPEC.format(py=sys.executable.replace("\\", "/")), encoding="utf-8")
        (self.root / "checks").mkdir()
        (self.root / "checks/test_greet.py").write_text(TEST, encoding="utf-8")
        (self.root / "app/greet.py").write_text("def greet():\n    return 'hello'\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "Add greet")

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_tests_then_gate(self):
        out = self.root / ".aidd" / "evidence"
        for in_place in (False, True):
            ev, _notes = test_runner.run_tests(repo=str(self.root), base="main", out_dir=str(out), red_in_place=in_place)
            by = {(r["name"], r["red_green"]): r for r in ev["results"]}
            self.assertEqual(by[("unit", "green")]["status"], "passed")
            self.assertEqual(by[("greet", "green")]["status"], "passed")
            self.assertEqual(by[("greet", "red")]["status"], "failed")
            self.assertEqual(by[("greet", "red")]["exit"], 1)
        self.assertEqual(gitutil.run(["status", "--porcelain", "--untracked-files=no"], str(self.root)).strip(), "")
        head = gitutil.rev_parse("HEAD", str(self.root))
        approvals = self.root / "approvals.json"
        approvals.write_text(
            json.dumps(
                {
                    "comments": [{"user": "bob", "body": f"/aidd approve-spec SPEC-1 {head}"}],
                    "reviews": [{"user": "bob", "state": "approved", "commit_sha": head}],
                }
            ),
            encoding="utf-8",
        )
        ctx = local_context.build_local_context(repo=str(self.root), base="main", approvals=str(approvals), evidence=str(out / "evidence.json"))
        d = decide(ctx)
        self.assertFalse(d.trusted)
        self.assertEqual(d.decision, "pass", [(f.rule, f.message) for f in d.findings])
        self.assertEqual(d.record["spec"], "specs/SPEC-1.md")

    def test_a_dirty_tree_is_recorded_and_its_green_is_no_evidence(self):
        """`aidd test` records what the tree holds beyond head; the gate then waits for a run in a clean tree. What git
        ignores, and aidd test's own output folder, keep a tree clean."""
        out = self.root / ".aidd" / "evidence"
        head = gitutil.rev_parse("HEAD", str(self.root))
        approvals = self.root / ".git" / "approvals.json"
        approvals.write_text(json.dumps({"reviews": [{"user": "bob", "state": "approved", "commit_sha": head}]}), encoding="utf-8")

        def run() -> tuple[dict, list[str], list[str]]:
            ev, notes = test_runner.run_tests(repo=str(self.root), base="main", out_dir=str(out))
            ctx = local_context.build_local_context(repo=str(self.root), base="main", approvals=str(approvals), evidence=str(out / "evidence.json"))
            return ev, notes, decide(ctx).codes()

        (self.root / "app" / "__pycache__").mkdir(exist_ok=True)
        (self.root / "app" / "__pycache__" / "x.pyc").write_bytes(b"ignored")
        ev, notes, codes = run()
        self.assertNotIn("dirty_tree", ev)
        self.assertNotIn("pending tests.dirty_tree", codes)
        self.assertFalse(any("dirty tree" in n for n in notes))
        with self.subTest("an untracked file git does not ignore"):
            (self.root / "app" / "scratch.py").write_text("x = 1\n", encoding="utf-8")
            ev, notes, codes = run()
            self.assertTrue(ev["dirty_tree"])
            self.assertEqual(ev["dirty_paths"], ["app/scratch.py"])
            self.assertIn("pending tests.dirty_tree", codes)
            fix = rulebook.BY_NAME["tests"].fix_for("tests.dirty_tree")
            self.assertTrue(any("(app/scratch.py)" in n and n.endswith(fix) for n in notes), notes)
            (self.root / "app" / "scratch.py").unlink()
        with self.subTest("a tracked change, staged or not"):
            (self.root / "app" / "greet.py").write_text("def greet():\n    return 'hi'\n", encoding="utf-8")
            ev, _, codes = run()
            self.assertEqual(ev["dirty_paths"], ["app/greet.py"])
            self.assertIn("pending tests.dirty_tree", codes)
            git(self.root, "add", "app/greet.py")
            self.assertEqual(run()[0]["dirty_paths"], ["app/greet.py"])
            git(self.root, "reset", "-q", "--hard")
        with self.subTest("a change git is told not to look at"):
            git(self.root, "update-index", "--assume-unchanged", "app/greet.py")
            (self.root / "app" / "greet.py").write_text("def greet():\n    return 'hi'\n", encoding="utf-8")
            self.assertNotIn("app/greet.py", gitutil.dirty(str(self.root), untracked=True), "git status must hide it, or this proves nothing")
            ev, _, codes = run()
            self.assertEqual(ev["dirty_paths"], ["app/greet.py"])
            self.assertIn("pending tests.dirty_tree", codes)
            git(self.root, "update-index", "--no-assume-unchanged", "app/greet.py")
            git(self.root, "update-index", "--skip-worktree", "app/greet.py")
            self.assertEqual(run()[0]["dirty_paths"], ["app/greet.py"])
            git(self.root, "update-index", "--no-skip-worktree", "app/greet.py")
            (self.root / "app" / "greet.py").write_text("def greet():\n    return 'hello'\n", encoding="utf-8")
        with self.subTest("a file only this clone's excludes or the person's global excludes hide, which CI never reads"):
            info_exclude = Path(git(self.root, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"))
            info_exclude.parent.mkdir(parents=True, exist_ok=True)
            before = info_exclude.read_text(encoding="utf-8") if info_exclude.is_file() else ""
            info_exclude.write_text(before + "app/local.py\n", encoding="utf-8")
            global_excludes = self.root.parent / f"{self.root.name}-global-excludes"
            global_excludes.write_text("app/global.py\n", encoding="utf-8")
            self.addCleanup(global_excludes.unlink)
            git(self.root, "config", "core.excludesFile", str(global_excludes))
            for name in ("local.py", "global.py"):
                (self.root / "app" / name).write_text("x = 1\n", encoding="utf-8")
            shown = gitutil.dirty(str(self.root), untracked=True)
            self.assertFalse({"app/local.py", "app/global.py"} & set(shown), "git status must hide both, or this proves nothing")
            ev, _, codes = run()
            self.assertEqual(ev["dirty_paths"], ["app/global.py", "app/local.py"])
            self.assertIn("pending tests.dirty_tree", codes)
            for name in ("local.py", "global.py"):
                (self.root / "app" / name).unlink()
            info_exclude.write_text(before, encoding="utf-8")
            git(self.root, "config", "--unset", "core.excludesFile")
        ev, _, codes = run()
        self.assertNotIn("dirty_tree", ev, "the earlier runs' evidence folder is aidd's own output")
        self.assertNotIn("pending tests.dirty_tree", codes)

    def test_init_and_doctor(self):
        fresh = Path(self.tmp.name) / "fresh"
        fresh.mkdir()
        git(fresh, "init", "-q")
        actions = adoption.init(fresh, adoption.InitOptions(profile="team", ci="github", links=[".claude/skills"]))
        self.assertTrue(any("vendored" in a for a in actions))
        self.assertTrue((fresh / ".claude/skills/aidd/SKILL.md").is_file())
        self.assertTrue((fresh / ".github/workflows/aidd-gate.yml").is_file())
        report = dict((m, lvl) for lvl, m in doctor_checks.doctor(fresh))
        self.assertEqual([m for m, lvl in report.items() if lvl == "fail"], ["profile team needs owners.approvers; " + config.EMPTY_APPROVERS])
        cfg = fresh / ".aidd/config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8").replace("approvers: []", 'approvers: ["@acme/leads"]', 1), encoding="utf-8")
        report = dict((m, lvl) for lvl, m in doctor_checks.doctor(fresh))
        self.assertFalse([m for m, lvl in report.items() if lvl == "fail"], report)
        again = adoption.init(fresh, adoption.InitOptions(profile="team", ci="github", links=[".claude/skills"]))
        self.assertTrue(all(not a.startswith("wrote") for a in again))


@unittest.skipUnless(shutil.which("git"), "git is required")
class GreenfieldTests(unittest.TestCase):
    """A new repository: day 0 holds only the aidd setup, and the first Spec brings the code, the runner, and the test."""

    def test_first_feature_on_an_empty_repository(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.email", "alice@example.com")
            git(root, "config", "user.name", "Alice")
            git(root, "config", "commit.gpgsign", "false")
            py = sys.executable.replace("\\", "/")
            (root / ".aidd").mkdir()
            # No `tests`: a greenfield repository has no suite yet.
            (root / ".aidd/config.yaml").write_text(CONFIG.format(py=py).split("\ntests:")[0], encoding="utf-8")
            git(root, "add", ".")
            git(root, "commit", "-qm", "Day 0: aidd setup")
            git(root, "checkout", "-qb", "feature")
            (root / "specs").mkdir()
            (root / "specs/SPEC-1.md").write_text(SPEC.format(py=py), encoding="utf-8")
            (root / "checks").mkdir()
            (root / "checks/test_greet.py").write_text(TEST, encoding="utf-8")
            (root / "app").mkdir()
            (root / "app/__init__.py").write_text("", encoding="utf-8")
            (root / "app/greet.py").write_text("def greet():\n    return 'hello'\n", encoding="utf-8")
            git(root, "add", ".")
            git(root, "commit", "-qm", "First feature")
            out = root / ".aidd" / "evidence"
            ev, _ = test_runner.run_tests(repo=str(root), base="main", out_dir=str(out))
            by = {(r["name"], r["red_green"]): r for r in ev["results"]}
            self.assertEqual(by[("greet", "green")]["status"], "passed")
            # On the empty base the code is missing, so the test fails by an import error: a valid red.
            self.assertEqual(by[("greet", "red")]["status"], "failed")
            self.assertNotIn(by[("greet", "red")]["exit"], (126, 127))
            head = gitutil.rev_parse("HEAD", str(root))
            approvals = root / "approvals.json"
            approvals.write_text(
                json.dumps(
                    {
                        "comments": [{"user": "bob", "body": f"/aidd approve-spec SPEC-1 {head}"}],
                        "reviews": [{"user": "bob", "state": "approved", "commit_sha": head}],
                    }
                ),
                encoding="utf-8",
            )
            ctx = local_context.build_local_context(repo=str(root), base="main", approvals=str(approvals), evidence=str(out / "evidence.json"))
            d = decide(ctx)
            self.assertEqual(d.decision, "pass", [(f.rule, f.message) for f in d.findings])


if __name__ == "__main__":
    unittest.main()
