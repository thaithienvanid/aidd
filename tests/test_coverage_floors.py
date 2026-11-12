"""The coverage summary gives line coverage and branch coverage on their own, and the floors never go down."""

import json
import unittest
from unittest import mock

import helpers  # noqa: F401  (puts src on sys.path)

import coverage_floors

# What `coverage report` counts: branches and lines together. These are the floors at the time the summary split them.
FLOORS_AT_SPLIT = {"the risk rules": 94, "everything": 90, "aidd-team's prototype tool": 86}


class CoverageSummaryTests(unittest.TestCase):
    def test_lines_and_branches_are_counted_apart(self):
        totals = {"covered_lines": 90, "num_statements": 100, "covered_branches": 15, "num_branches": 30}
        self.assertEqual(coverage_floors.line_and_branch(totals), ("90.0%", "50.0%"))

    def test_a_run_without_branches_says_so_instead_of_dividing_by_zero(self):
        self.assertEqual(coverage_floors.line_and_branch({"covered_lines": 1, "num_statements": 2}), ("50.0%", "n/a"))

    def test_the_summary_reads_coverage_json_and_says_unknown_when_coverage_cannot_answer(self):
        said = json.dumps({"totals": {"covered_lines": 3, "num_statements": 4, "covered_branches": 1, "num_branches": 2}})
        with mock.patch("subprocess.run", return_value=mock.Mock(stdout=said)):
            self.assertEqual(coverage_floors.separately("src/aidd/*"), ("75.0%", "50.0%"))
        with mock.patch("subprocess.run", return_value=mock.Mock(stdout="")):
            self.assertEqual(coverage_floors.separately("src/aidd/*"), ("?", "?"))

    def test_no_floor_is_lower_than_it_was_when_the_summary_split_them(self):
        floors = {what: floor for what, _include, floor in coverage_floors.FLOORS}
        for what, was in FLOORS_AT_SPLIT.items():
            self.assertGreaterEqual(floors[what], was, f"the floor for {what} only rises; add tests instead of lowering it")


if __name__ == "__main__":
    unittest.main()
