"""tests/run.py, the parallel runner: a file passes only when its process exits 0 and it ran at least one test.

Python 3.11's unittest exits 0 when it collects no tests, and 3.12 and later exit 5, so the exit code alone would pass a
file that proves nothing on 3.11. The runner reads the count from unittest's summary on stderr as well.
"""

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


if __name__ == "__main__":
    unittest.main()
