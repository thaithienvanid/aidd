"""Every repository a team eval case builds is a valid aidd repository in today's shape: the first third of the cases, by a checksum of
the name, and the one fixture all the trigger cases share. See test_eval_fixtures_plugin and tests/eval_fixture_repos.py.

The trigger cases are written from `evals/team/triggers.json` and share one fixture, so it is built once.
"""

import tempfile
import unittest
from pathlib import Path

from eval_fixture_repos import check, check_suite, listed_cases_exist

from aidd.evals import trigger_cases

SUITE = "team"


class TeamFixturesAreInTodaysShape(unittest.TestCase):
    def test_each_case_builds_a_repository_aidd_accepts(self):
        check_suite(self, SUITE, 0, 3)

    def test_the_fixture_every_trigger_case_shares_builds_a_repository_aidd_accepts(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "fixture.sh"
            fixture.write_text(trigger_cases.FIXTURE, encoding="utf-8")
            check(self, f"{SUITE}/the trigger cases' shared fixture", fixture)

    def test_the_stale_by_design_list_names_cases_that_exist(self):
        listed_cases_exist(self, SUITE)


if __name__ == "__main__":
    unittest.main()
