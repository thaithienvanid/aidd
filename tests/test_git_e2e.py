"""End to end in a throwaway git repository: init, doctor, `aidd test` (green and red), a local gate."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, git  # noqa: F401  (ROOT puts src on sys.path)

from aidd import gitutil, localctx, model, repo, runner
from aidd.verify import verify

CONFIG = """aidd_version = "1.0.0"
profile = "team"

[owners]
approvers = ["bob"]
[owners.reviewers]
security = ["@sec"]

[[tests]]
name = "unit"
command = ["{py}", "-c", "print('suite ok')"]
"""

SPEC = """+++
aidd_version = "1.0.0"
kind = "spec"
id = "SPEC-1"
title = "Greeting says hello"
owner_team = "core"
type = "feat"
route = "normal"
confidence = "high"
open_questions = []
trace_id = "spec-1"
assisted_by = []
rollback = "Revert the PR."

[risk]
summary = "Adds a greeting function."
dimensions = []
reversible = true

[[tasks]]
id = "T1"
title = "Implement greet"
scope = ["app/"]

[tests]
files = ["checks/test_greet.py"]

[[tests.commands]]
name = "greet"
command = ["{py}", "checks/test_greet.py"]
new_behavior = true
+++

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
        (self.root / ".aidd/config.toml").write_text(CONFIG.format(py=sys.executable.replace("\\", "/")), encoding="utf-8")
        (self.root / "app").mkdir()
        (self.root / "app/__init__.py").write_text("", encoding="utf-8")
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
        out = self.root / "aidd-evidence"
        for in_place in (False, True):
            ev, _notes = runner.run_tests(repo=str(self.root), base="main", out_dir=str(out), red_in_place=in_place)
            by = {(r["name"], r["phase"]): r for r in ev["results"]}
            self.assertEqual(by[("unit", "green")]["status"], "passed")
            self.assertEqual(by[("greet", "green")]["status"], "passed")
            self.assertEqual(by[("greet", "red")]["status"], "failed")
            self.assertEqual(by[("greet", "red")]["exit"], 1)
        self.assertEqual(gitutil.run(["status", "--porcelain", "--untracked-files=no"], str(self.root)).strip(), "")
        head = gitutil.rev_parse("HEAD", str(self.root))
        text = (self.root / "specs/SPEC-1.md").read_text(encoding="utf-8")
        h = model.spec_hash(text, gitutil.ls_tree(head, str(self.root)))
        approvals = self.root / "approvals.json"
        approvals.write_text(
            json.dumps(
                {
                    "comments": [{"user": "bob", "body": f"/aidd approve-spec SPEC-1 {h}"}],
                    "reviews": [{"user": "bob", "state": "approved", "commit_sha": head}],
                }
            ),
            encoding="utf-8",
        )
        ctx = localctx.build(repo=str(self.root), base="main", approvals=str(approvals), evidence=str(out / "evidence.json"))
        d = verify(ctx)
        self.assertFalse(d.trusted)
        self.assertEqual(d.decision, "pass", [(f.rule, f.message) for f in d.findings])
        self.assertEqual(d.record["spec"], "specs/SPEC-1.md")

    def test_init_and_doctor(self):
        fresh = Path(self.tmp.name) / "fresh"
        fresh.mkdir()
        git(fresh, "init", "-q")
        actions = repo.init(fresh, profile="team", ci="github", links=[".claude/skills"])
        self.assertTrue(any("vendored" in a for a in actions))
        self.assertTrue((fresh / ".claude/skills/aidd/SKILL.md").is_file())
        self.assertTrue((fresh / ".github/workflows/aidd-gate.yml").is_file())
        report = dict((m, lvl) for lvl, m in repo.doctor(fresh))
        self.assertEqual([m for m, lvl in report.items() if lvl == "fail"], ["profile team needs owners.approvers; " + repo.EMPTY_APPROVERS])
        cfg = fresh / ".aidd/config.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8").replace("approvers = []", 'approvers = ["@acme/leads"]', 1), encoding="utf-8")
        report = dict((m, lvl) for lvl, m in repo.doctor(fresh))
        self.assertFalse([m for m, lvl in report.items() if lvl == "fail"], report)
        again = repo.init(fresh, profile="team", ci="github", links=[".claude/skills"])
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
            # No [[tests]]: a greenfield repository has no suite yet.
            (root / ".aidd/config.toml").write_text(CONFIG.format(py=py).split("[[tests]]")[0], encoding="utf-8")
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
            out = root / "aidd-evidence"
            ev, _ = runner.run_tests(repo=str(root), base="main", out_dir=str(out))
            by = {(r["name"], r["phase"]): r for r in ev["results"]}
            self.assertEqual(by[("greet", "green")]["status"], "passed")
            # On the empty base the code is missing, so the test fails by an import error: a valid red.
            self.assertEqual(by[("greet", "red")]["status"], "failed")
            self.assertNotIn(by[("greet", "red")]["exit"], (126, 127))
            head = gitutil.rev_parse("HEAD", str(root))
            h = model.spec_hash((root / "specs/SPEC-1.md").read_text(encoding="utf-8"), gitutil.ls_tree(head, str(root)))
            approvals = root / "approvals.json"
            approvals.write_text(
                json.dumps(
                    {
                        "comments": [{"user": "bob", "body": f"/aidd approve-spec SPEC-1 {h}"}],
                        "reviews": [{"user": "bob", "state": "approved", "commit_sha": head}],
                    }
                ),
                encoding="utf-8",
            )
            ctx = localctx.build(repo=str(root), base="main", approvals=str(approvals), evidence=str(out / "evidence.json"))
            d = verify(ctx)
            self.assertEqual(d.decision, "pass", [(f.rule, f.message) for f in d.findings])


if __name__ == "__main__":
    unittest.main()
