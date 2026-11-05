"""Every repository a plugin eval case builds is a valid aidd repository in today's shape, so a case never fails on a stale fixture.

A case's `fixture.sh` is built as the eval runner builds it, with no model and no agent, and `aidd validate` and the part of
`aidd upgrade` that migrates retired names read the result. tests/eval_fixture_repos.py lists the cases that are stale on purpose,
with the reason for each, and shares the team suite's cases out over three files so each stays inside the time budget.
"""

import unittest

from eval_fixture_repos import check_suite, listed_cases_exist

SUITE = "plugin"


class PluginFixturesAreInTodaysShape(unittest.TestCase):
    def test_each_case_builds_a_repository_aidd_accepts(self):
        check_suite(self, SUITE)

    def test_the_stale_by_design_list_names_cases_that_exist(self):
        listed_cases_exist(self, SUITE)


if __name__ == "__main__":
    unittest.main()
