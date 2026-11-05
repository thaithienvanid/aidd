"""tests/run.py, the parallel runner: a file passes only when its process exits 0 and it ran at least one test.

Python 3.11's unittest exits 0 when it collects no tests, and 3.12 and later exit 5, so the exit code alone would pass a
file that proves nothing on 3.11. The runner reads the count from unittest's summary on stderr as well.
"""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import run

TWO_TESTS_ONE_SKIPPED = """import unittest


class T(unittest.TestCase):
    def test_one(self):
        print("Ran 9 tests")

    @unittest.skip("on purpose")
    def test_two(self):
        pass
"""


class RunnerVerdictTests(unittest.TestCase):
    def test_a_file_passes_only_with_exit_0_and_a_test_run(self):
        self.assertTrue(run.Result("t", 0, 0.1, 3, 0, "").passed)
        self.assertFalse(run.Result("t", 0, 0.1, 0, 0, "").passed)  # Python 3.11, no tests collected
        self.assertFalse(run.Result("t", 5, 0.1, 0, 0, "").passed)  # Python 3.12 and later, no tests collected
        self.assertFalse(run.Result("t", 1, 0.1, 3, 0, "").passed)

    def test_the_counts_come_from_the_last_summary(self):
        summary = "...\n" + "-" * 70 + "\nRan 4 tests in 0.010s\n\nOK (skipped=2)\n"
        self.assertEqual(run.counts(summary), (4, 2))
        self.assertEqual(run.counts("Ran 9 tests\n" + summary), (4, 2))  # a line a test printed comes first
        self.assertEqual(run.counts("Ran 1 test in 0.001s\n\nFAILED (failures=1, skipped=1)\n"), (1, 1))
        self.assertEqual(run.counts("Ran 0 tests in 0.000s\n\nNO TESTS RAN\n"), (0, 0))
        self.assertEqual(run.counts("Traceback: the interpreter never reached unittest\n"), (0, 0))

    def test_the_counts_read_this_python_s_own_summary(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "test_tiny.py").write_text(TWO_TESTS_ONE_SKIPPED, encoding="utf-8")
            done = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", d, "-p", "test_tiny.py"], capture_output=True, text=True, check=False, timeout=60
            )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(run.counts(done.stderr), (2, 1), done.stderr)

    def test_a_file_that_collects_no_tests_fails_on_every_python(self):
        result = run.run_one(Path("test_no_such_file_for_the_runner.py"), coverage=False)
        self.assertEqual(result.ran, 0, result.output)
        self.assertFalse(result.passed, result.output)
        if result.code == 0:  # Python 3.11: the runner says why it fails
            self.assertIn("ran no tests", result.output)
        else:
            self.assertEqual(result.code, 5, result.output)


def load_read_record():
    """tests/record_reads/sitecustomize.py under another name, so it records nothing here and only lends its rules."""
    spec = importlib.util.spec_from_file_location("record_reads_rules", run.RECORDER / "sitecustomize.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ChangedSelectionTests(unittest.TestCase):
    """`--changed` runs a file when it read what changed. A file it skips must be one the change cannot affect."""

    RECORD = {
        "files": {
            "test_reads_x": ["src/aidd/x.py", "schemas/a.json"],
            "test_anything": ["*", "# bash: it runs inside the checkout"],
            "test_checks_new": ["?docs/new.md"],
            "test_lists_docs": ["docs/"],
            "test_reads_y": ["src/aidd/y.py"],
        }
    }
    EVERY = ["test_reads_x", "test_anything", "test_checks_new", "test_lists_docs", "test_reads_y", "test_unrecorded"]

    def test_the_files_a_change_can_affect(self):
        cases = [
            ({"src/aidd/x.py"}, set(), {"test_reads_x"}),
            ({"schemas/a.json"}, set(), {"test_reads_x"}),
            ({"docs/new.md"}, {"docs/new.md"}, {"test_checks_new", "test_lists_docs"}),
            ({"docs/guides/new.md"}, {"docs/guides/new.md"}, {"test_lists_docs"}),  # a new folder shows in its parent's list
            ({"docs/old.md"}, set(), set()),
            ({"tests/test_reads_y.py"}, set(), {"test_reads_y"}),
            (set(), set(), set()),
        ]
        for changed, moved, expected in cases:
            with self.subTest(changed=changed, moved=moved):
                picked = run.affected(self.RECORD, changed, moved, self.EVERY)
                self.assertEqual(picked, expected | {"test_anything", "test_unrecorded"})

    def test_a_child_whose_reads_the_record_cannot_see(self):
        rules = load_read_record()
        root = str(run.ROOT)
        with tempfile.TemporaryDirectory() as outside:
            env = {"PATH": "/usr/bin:/bin", "HOME": outside}
            traced = {**env, rules.LOG: f"{outside}/log", "PYTHONPATH": os.pathsep.join([f"{root}/src", rules.HERE])}
            cases = [
                (["git", "status"], outside, env, False),
                (["git", "ls-files"], root, env, True),
                (["git", "-c", "core.quotePath=false", "rev-parse", "--show-toplevel"], root, env, False),  # git's own state only
                (["git", "init", "-q", f"{outside}/repo"], root, env, False),
                (["rm", "-rf", f"{outside}/repo"], root, env, False),
                (["rm", "-rf", "build"], root, env, True),
                (["bash", "-c", f"cat {root}/README.md"], outside, env, True),
                (["sh"], outside, env, True),  # its commands come on standard input
                (["env", "-i", "python3", "-m", "aidd"], outside, env, True),
                ([sys.executable, "-m", "aidd", "gate"], outside, traced, False),
                ([sys.executable, "-I", "-c", f"import sys; sys.path[:0] = ['{root}/src']"], outside, traced, True),
                ([sys.executable, "-m", "aidd", "gate"], outside, {**env, "PYTHONPATH": f"{root}/src"}, True),
                (["node", "hook.js"], outside, {**env, "CLAUDE_PLUGIN_ROOT": f"{root}/plugins/aidd-team"}, True),
            ]
            for argv, cwd, environ, expected in cases:
                with self.subTest(argv=argv, cwd=cwd):
                    self.assertEqual(bool(rules.unseen(argv[0], argv, cwd, environ)), expected)
            # Listing the checkout's file names reads its folders, not everything; with content ids it reads more.
            self.assertEqual(rules.unseen("git", ["git", "ls-files", "-z"], root, env), rules.LISTS_CHECKOUT)
            self.assertNotIn(rules.unseen("git", ["git", "ls-files", "-s"], root, env), ("", rules.LISTS_CHECKOUT))
            self.assertEqual(rules.unseen("git", ["git", "-C", f"{outside}/repo", "log"], root, env), "")
            self.assertEqual(rules.unseen("ssh-keygen", ["ssh-keygen", "-q", "-t", "ed25519", "-f", f"{outside}/key"], root, env), "")

    def test_python_options_that_skip_the_record(self):
        rules = load_read_record()
        for argv, expected in [
            (["python3", "-I", "-c", "x"], True),
            (["python3", "-Ic", "x"], True),
            (["python3", "-X", "importtime", "-E", "x.py"], True),
            (["python3", "-c", "-I"], False),
            (["python3", "-m", "aidd", "-I"], False),
            (["python3", "-u", "x.py"], False),
        ]:
            with self.subTest(argv=argv):
                self.assertEqual(rules.isolated(argv), expected)

    def test_the_budget_names_each_slow_file_and_the_wall_time(self):
        results = [run.Result("test_slow", 0, run.FILE_BUDGET_SECONDS + 5, 1, 0, ""), run.Result("test_quick", 0, 1.0, 1, 0, "")]
        over = "\n".join(run.budget_report(results, run.WALL_BUDGET_SECONDS + 30))
        self.assertIn("test_slow", over)
        self.assertNotIn("test_quick", over)
        self.assertIn("30.0s over", over)
        self.assertIn("inside the budget", "\n".join(run.budget_report(results[1:], 60)))


if __name__ == "__main__":
    unittest.main()
