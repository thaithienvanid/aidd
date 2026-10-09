"""Local speed: `aidd test --changed` and `--watch` (partial evidence the gate never accepts), and `aidd observe --window`."""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, git, run_cli  # noqa: F401  (ROOT puts src on sys.path)
from test_git_e2e import CONFIG, SPEC, TEST

from aidd import localctx, observe, runner
from aidd.verify import verify

DOCS_CHECK = """
[[tests]]
name = "docs"
command = ["{py}", "-c", "print('docs ok')"]
when_changed = ["docs/**"]
"""


@unittest.skipUnless(shutil.which("git"), "git is required")
class ChangedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        py = sys.executable.replace("\\", "/")
        git(self.root, "init", "-q", "-b", "main")
        for k, v in (("user.email", "alice@example.com"), ("user.name", "Alice"), ("commit.gpgsign", "false")):
            git(self.root, "config", k, v)
        (self.root / ".aidd").mkdir()
        (self.root / ".aidd/config.toml").write_text(CONFIG.format(py=py) + DOCS_CHECK.format(py=py), encoding="utf-8")
        (self.root / ".gitignore").write_text("aidd-evidence/\n", encoding="utf-8")
        (self.root / "app").mkdir()
        (self.root / "app/__init__.py").write_text("", encoding="utf-8")
        (self.root / "docs").mkdir()
        (self.root / "docs/guide.md").write_text("guide\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "base")
        git(self.root, "checkout", "-qb", "feature")
        (self.root / "specs").mkdir()
        (self.root / "specs/SPEC-1.md").write_text(SPEC.format(py=py), encoding="utf-8")
        (self.root / "checks").mkdir()
        (self.root / "checks/test_greet.py").write_text(TEST, encoding="utf-8")
        (self.root / "app/greet.py").write_text("def greet():\n    return 'hello'\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "Add greet")
        self.out = self.root / "aidd-evidence"

    def tearDown(self):
        self.tmp.cleanup()

    def names(self, ev):
        return sorted((r["name"], r["red_green"]) for r in ev["results"])

    def test_changed_runs_what_the_working_tree_selects_green_only_and_marks_it_partial(self):
        ev, notes = runner.run_tests(repo=str(self.root), base="main", out_dir=str(self.out), changed=True)
        # The Spec's command runs (its Task scope changed), the suite runs, the docs check does not; no red phase.
        self.assertEqual(self.names(ev), [("greet", "green"), ("unit", "green")])
        self.assertIs(ev["partial"], True)
        self.assertTrue(any(n.startswith("partial:") for n in notes))
        # An uncommitted docs edit selects the docs check too.
        (self.root / "docs/guide.md").write_text("guide, edited\n", encoding="utf-8")
        ev, _ = runner.run_tests(repo=str(self.root), base="main", out_dir=str(self.out), changed=True)
        self.assertEqual(self.names(ev), [("docs", "green"), ("greet", "green"), ("unit", "green")])

    def test_the_gate_never_accepts_partial_evidence(self):
        ev, _ = runner.run_tests(repo=str(self.root), base="main", out_dir=str(self.out), changed=True)
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            ctx = localctx.build(base="main", body=localctx.spec_block("specs/SPEC-1.md"), run_policy=False)
        finally:
            os.chdir(cwd)
        ctx["evidence"] = ev
        d = verify(ctx)
        self.assertNotEqual(d.decision, "pass")
        self.assertIn("pending tests.evidence_partial", d.codes())
        # The same run without --changed is full evidence: the partial finding goes away.
        ctx["evidence"], _ = runner.run_tests(repo=str(self.root), base="main", out_dir=str(self.out))
        self.assertNotIn("pending tests.evidence_partial", verify(ctx).codes())

    def test_select_changed_needs_a_matching_path(self):
        spec_cmd = ({"name": "s", "command": ["x"]}, "spec")
        suite = ({"name": "u", "command": ["y"]}, "config")
        declared = {"tasks": [{"scope": ["app/"]}], "tests": {"files": ["checks/test_greet.py"]}}
        self.assertEqual(runner.select_changed([spec_cmd, suite], declared, []), [])
        self.assertEqual(runner.select_changed([spec_cmd, suite], declared, ["README.md"]), [suite])
        self.assertEqual(runner.select_changed([spec_cmd, suite], declared, ["checks/test_greet.py"]), [spec_cmd, suite])

    def test_watch_reruns_on_a_change_and_stops_on_ctrl_c(self):
        runs = []
        sleeps = iter(range(10))

        def sleep(_):
            n = next(sleeps)
            if n == 1:
                (self.root / "app/greet.py").write_text("def greet():\n    return 'hello!'\n", encoding="utf-8")
            if n == 3:
                raise KeyboardInterrupt

        code = runner.watch(lambda: runs.append(1), repo=str(self.root), interval=0, exclude="aidd-evidence", sleep=sleep)
        self.assertEqual((code, len(runs)), (0, 2))

    def test_watch_ignores_what_the_run_itself_writes_to_the_evidence_folder(self):
        runs = []

        def run_once():
            runs.append(1)
            self.out.mkdir(exist_ok=True)
            (self.out / "evidence.json").write_text(str(len(runs)), encoding="utf-8")

        sleeps = iter(range(3))

        def sleep(_):
            if next(sleeps) == 2:
                raise KeyboardInterrupt

        runner.watch(run_once, repo=str(self.root), interval=0, exclude="aidd-evidence", sleep=sleep)
        self.assertEqual(len(runs), 1)

    def test_cli_changed_prints_partial(self):
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            code, out = run_cli("test", "--changed", "--base", "main")
        finally:
            os.chdir(cwd)
        self.assertEqual(code, 0, out)
        self.assertIn("partial", out)


OBSERVED_SPEC = """+++
kind = "spec"
id = "SPEC-9"

[observe]
window = "24h"
rollback_trigger = "error rate above 1% for 5 minutes"
command = {command}
+++
"""


class ObserveWindowTests(unittest.TestCase):
    def fake_time(self):
        now = [0.0]
        return (lambda: now[0]), (lambda s: now.__setitem__(0, now[0] + s))

    def test_a_clean_window_passes_after_its_last_check(self):
        clock, sleep = self.fake_time()
        w = observe.watch_window(lambda: 0, window_s=3600, every_s=900, clock=clock, sleep=sleep, report=lambda _: None)
        self.assertEqual((w.result, w.checks), ("pass", 5))  # at 0, 15, 30, 45, and 60 minutes

    def test_the_trigger_fires_after_enough_failures_in_a_row(self):
        clock, sleep = self.fake_time()
        codes = iter([0, 1, 0, 1, 1, 0])
        w = observe.watch_window(lambda: next(codes), window_s=86400, every_s=60, consecutive=2, clock=clock, sleep=sleep, report=lambda _: None)
        self.assertEqual((w.result, w.checks, w.failures), ("fail", 5, 3))

    def test_durations(self):
        self.assertEqual([observe.seconds(x) for x in ("90s", "30m", "24h", "7d")], [90, 1800, 86400, 604800])
        with self.assertRaises(ValueError):
            observe.seconds("1w")

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_cli_window_exit_codes_and_it_never_rolls_back(self):
        py = sys.executable.replace("\\", "/")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            git(root, "init", "-q", "-b", "main")
            spec = root / "specs/SPEC-9.md"
            spec.parent.mkdir()
            cwd = os.getcwd()
            os.chdir(root)
            try:
                spec.write_text(OBSERVED_SPEC.format(command=f'["{py}", "-c", "raise SystemExit(3)"]'), encoding="utf-8")
                code, out = run_cli("observe", "specs/SPEC-9.md", "--window", "1h", "--every", "1s")
                self.assertEqual(code, 1, out)
                self.assertIn("ROLLBACK TRIGGER FIRED", out)
                self.assertIn("never rolls back", out)
                spec.write_text(OBSERVED_SPEC.format(command=f'["{py}", "-c", "pass"]'), encoding="utf-8")
                code, out = run_cli("observe", "specs/SPEC-9.md", "--window", "1s", "--every", "1s")
                self.assertEqual(code, 0, out)
                self.assertIn("the rollback trigger never fired", out)
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
