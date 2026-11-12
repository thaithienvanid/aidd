"""Every repository a team eval case builds is a valid aidd repository in today's shape: the last third of the cases, by a checksum of
the name. See test_eval_fixtures_team_1 and tests/eval_fixture_repos.py."""

import unittest

from eval_fixture_repos import check_suite


class TeamFixturesAreInTodaysShape(unittest.TestCase):
    def test_each_case_builds_a_repository_aidd_accepts(self):
        check_suite(self, "team", 2, 3)


if __name__ == "__main__":
    unittest.main()
