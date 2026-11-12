"""The honest sequences of a revision that one change cannot make green, run as CI runs them (`aidd test --require-green`).

Invariant: every command the base holds that the head changes or removes runs on the head as `base.<name>` and must pass there. So a
command goes in two changes, never in one that breaks what it checked: the first keeps the old command and its test file working
and adds the new one beside it, the second drops the old command, and a third deletes the file and the code that no command runs.
Each step needs the person who agreed to the revision to approve the Spec again, and none needs a bypass of a required check. A Spec
and its failing test cannot land alone, because the check is red until the code makes it green.
"""

from __future__ import annotations

import unittest

from test_spec_revision import CHECK, NEW, OLD, RENAMED_NEW, Shapes, greet_code, greet_test


class SequencesTests(Shapes):
    def green(self, head: str, results: set[tuple[str, str, str]]) -> None:
        """CI's run on `head` exits 0 with exactly these results besides the repository suite, and the head merges into `main`."""
        code, ran, notes = self.shown(head)
        self.assertEqual((code, {r for r in ran if r[0] != "unit"}), (0, results), notes)
        self.merge(head)

    def test_a_rename_in_three_changes(self):
        both = [*OLD, *NEW]
        one = self.revise(self.spec([RENAMED_NEW], NEW), {"checks/test_greet.py": None, "checks/test_greeting.py": greet_test("hello")}, {})
        code, ran, _ = self.shown(one)
        self.assertEqual((code, ("base.check", "green", "failed") in ran), (1, True), "in one change the old file is gone, so the base's copy fails")
        self.fresh()
        self.green(
            self.revise(self.spec([CHECK, RENAMED_NEW], both), {"checks/test_greeting.py": greet_test("hello")}, {}),
            {("check", "green", "passed"), ("check_v2", "green", "passed")},
        )
        self.green(self.revise(self.spec([RENAMED_NEW], both), {}, {}), {("base.check", "green", "passed"), ("check_v2", "green", "passed")})
        self.green(self.revise(self.spec([RENAMED_NEW], NEW), {"checks/test_greet.py": None}, {}), {("check_v2", "green", "passed")})

    def test_retiring_behavior_in_two_changes(self):
        both = [*OLD, "checks/test_loud.py"]
        self.land_loud()
        self.green(
            self.revise(self.spec([CHECK], both), {}, {}),
            {("check", "green", "passed"), ("base.check_loud", "green", "passed")},
        )
        self.green(self.revise(self.spec([CHECK], OLD), {"checks/test_loud.py": None}, {"app/loud.py": None}), {("check", "green", "passed")})

    def test_a_new_expectation_in_a_renamed_file_goes_in_place_first(self):
        """The expectation changes in the file the command already names (shape a), and the rename follows as a rename."""
        self.green(self.shape("a"), {("check", "green", "passed")})

    def test_a_spec_and_its_failing_test_cannot_land_alone(self):
        """Shape (f): red, so a required check blocks it. Only a bypass lands it, and the code that follows is a change like any other."""
        head = self.shape("f")
        code, ran, _ = self.shown(head)
        self.assertEqual((code, ("check", "green", "failed") in ran), (1, True))
        self.merge(head, status="approved")  # a person's bypass of the required check, simulated: the Spec is approved, not built
        self.branch("code")
        later = self.finish({"app/greet.py": greet_code("hello, world")})
        code, ran, notes = self.shown(later)
        self.assertEqual(code, 0)
        self.assertNotIn(("check", "green", "passed"), ran, "the Spec's tests do not run: the change only reaches its scope")
        self.assertTrue(any("did not run" in n for n in notes), notes)


if __name__ == "__main__":
    unittest.main()
