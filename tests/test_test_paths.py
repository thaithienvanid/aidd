"""One list says what a test file is: `test_paths` in the built-in risk rules. The route advice, `aidd init`, and the
delegate check's "every test file the base holds stays unchanged" check all read it. Before, three lists disagreed, and the
check missed `e2e/` and `testing/`. Nothing any of the three counted as a test file may stop counting."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import git
from test_delegation_check import Case

from aidd import config, risk
from aidd.delegation import diff_signals
from aidd.setup import detection
from aidd.config import model

# What the three old lists each counted: the route advice's pattern, `aidd init`'s names and folders, and the delegate
# check's globs. Every path here is a test file now, in each reader.
WHAT_THE_ROUTE_ADVICE_COUNTED = [
    "tests/a.py",
    "src/test/a.py",
    "web/__tests__/a.js",
    "spec/a.rb",
    "e2e/a.ts",
    "testing/a.py",
    "test_a.py",
    "pkg/test_a.py",
    "a_test.py",
    "pkg/a_test.go",
    "a_test.rb",
    "a_test.dart",
    "a.test.ts",
    "a.spec.jsx",
    "a.test.mjs",
    "a.spec.cts",
    "FooTest.java",
    "FooTests.cs",
    "FooTest.kt",
    "a_spec.rb",
]
WHAT_INIT_COUNTED = [
    "test_x.py",
    "x_test.py",
    "x_test.go",
    "x.test.js",
    "x.spec.tsx",
    "Test.java",
    "Tests.cs",
    "Test.cs",
    "x_spec.rb",
    "x_test.rb",
    "x_test.dart",
] + [f"{d}/x.py" for d in ("test", "tests", "testing", "__tests__", "spec", "specs_test", "e2e")]
WHAT_THE_DELEGATE_CHECK_COUNTED = [
    "a/x.spec.py",
    "a/x.test.php",
    "a/x_test.c",
    "a/FooTest.swift",
    "a/FooTests.go",
    "a/__tests__/x",
    "a/spec/x",
    "a/test/x",
    "a/test_x.sh",
    "a/tests/x",
]
# Source that no reader may take for a test: a word that holds `test` inside a longer one, and a folder only named alike.
NOT_TESTS = [
    "src/cart.py",
    "src/latest.py",
    "src/contest.rb",
    "src/attest.go",
    "src/protest.ts",
    "src/testing_utils.py",
    "src/contest/main.py",
    "docs/testimony.md",
    "src/inspect.py",
]


class OneListForEveryReader(unittest.TestCase):
    def test_nothing_an_old_list_counted_stops_counting(self):
        for path in WHAT_THE_ROUTE_ADVICE_COUNTED + WHAT_INIT_COUNTED + WHAT_THE_DELEGATE_CHECK_COUNTED:
            with self.subTest(path=path):
                self.assertTrue(config.looks_like_test(path))

    def test_the_case_must_match_unless_the_delegate_check_folds_it(self):
        for path in ("Tests/Test_Cart.py", "E2E/Flow.ts"):
            with self.subTest(path=path):
                self.assertFalse(config.looks_like_test(path))
                self.assertTrue(config.looks_like_test(path, fold_case=True))

    def test_the_list_is_broader_than_each_old_one_and_that_is_accepted(self):
        # The union is the floor, so the delegate check never loosens. The cost: a file only one old list took for a test now
        # reads as one everywhere, so the route advice no longer asks for a test before such a file. These are pinned.
        broader = {
            "bin/test": "a script named test",
            "src/components/ABTest.tsx": "a name that ends in Test",
            "docs/api_spec.yaml": "a name that ends in _spec",
        }
        for path, why in broader.items():
            with self.subTest(path=path, why=why):
                self.assertTrue(config.looks_like_test(path))
                self.assertNotIn("write a test for the new code", risk.advice(None, ["src/cart_total.py", path], tracked=[])["next"]["what"])

    def test_no_word_that_only_holds_test_is_one(self):
        for path in NOT_TESTS:
            with self.subTest(path=path):
                self.assertFalse(config.looks_like_test(path))

    def test_the_list_is_data_and_has_one_owner(self):
        self.assertEqual(model.test_paths(), risk.builtin()["test_paths"])
        self.assertNotIn("test_paths", risk.builtin()["delegation"], "the delegation block holds no list of its own")

    def test_a_planned_test_file_means_the_change_names_its_tests(self):
        new = "src/cart_total.py"
        for path in ("e2e/cart.spec.ts", "src/cart_total_test.ts", "testing/fixtures.py"):
            with self.subTest(path=path):
                step = risk.advice(None, [new, path], tracked=[])["next"]["what"]
                self.assertNotIn("write a test for the new code", step)
        self.assertIn("write a test for the new code", risk.advice(None, [new], tracked=[])["next"]["what"])


class TheDelegateCheckSeesEveryTestFolder(Case):
    def changed(self, tests: list[str]) -> list[str]:
        """The test files of `tests` the delegate check finds changed, when every file in `tests` and src/cart.py gains a line."""
        repo = self.repo()
        git(self.root, "checkout", "-q", "main")
        for path in [*tests, "src/cart.py"]:
            repo.write(path, "one\n")
        repo.commit("tests and code")
        git(self.root, "checkout", "-q", "-B", "feature")
        for path in [*tests, "src/cart.py"]:
            repo.write(path, "one\ntwo\n")
        return diff_signals.changed_test_files("main", repo.change(), str(self.root))

    def test_a_changed_test_file_defers_in_any_test_folder(self):
        tests = ["tests/test_cart.py", "e2e/checkout.spec.ts", "e2e/helpers.ts", "testing/fixtures.py", "src/cart_test.ts", "spec/cart_spec.rb"]
        self.assertEqual(self.changed(tests), sorted(tests))

    def test_the_check_ignores_case_where_the_other_readers_do_not(self):
        # No folder here has a twin that differs in case, since a case-folding disk would merge them.
        tests = ["Tests/Test_Cart.py", "E2E/Flow.ts", "__Tests__/Cart.js"]
        self.assertEqual(self.changed(tests), sorted(tests))


class InitCountsTheSameFiles(unittest.TestCase):
    def untested(self, *files: str) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            for rel in files:
                (Path(tmp) / rel).parent.mkdir(parents=True, exist_ok=True)
                (Path(tmp) / rel).write_text("", encoding="utf-8")
            return detection.detect(Path(tmp))["untested"]

    def test_code_beside_a_test_file_of_any_list_entry_is_tested(self):
        for test in ("app/cart_test.ts", "app/cart.spec.py", "app/tests/unit/cart.py", "app/e2e/flow.ts", "app/testing/fixtures.py"):
            with self.subTest(test=test):
                self.assertEqual(self.untested("app/cart.py", test), [])

    def test_code_with_no_test_is_still_untested(self):
        self.assertEqual(self.untested("app/cart.py", "app/latest.py"), ["app"])

    def test_a_test_folder_is_not_code_without_tests(self):
        for folder in ("e2e", "testing", "test", "spec", "specs_test"):
            with self.subTest(folder=folder):
                self.assertEqual(self.untested(f"{folder}/flow.ts", "app/cart.py", f"{folder}/more/flow.ts"), ["app"])


if __name__ == "__main__":
    unittest.main()
