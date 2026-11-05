"""The verdict of an `aidd test` run: which results are good, and the exit code the run ends with."""

from __future__ import annotations

import unittest

import helpers  # noqa: F401

from aidd import testing

GREEN_PASS = {"red_green": "green", "status": "passed", "exit": 0}
GREEN_FAIL = {"red_green": "green", "status": "failed", "exit": 1}
RED_FAIL = {"red_green": "red", "status": "failed", "exit": 1}
RED_PASS = {"red_green": "red", "status": "passed", "exit": 0}
EXPECTED = {**GREEN_FAIL, "before_implement": True}  # a failing run the runner expected before Implement


class VerdictTests(unittest.TestCase):
    def test_a_mark_for_each_result(self):
        cases = [
            (GREEN_PASS, False, "ok"),
            (RED_FAIL, False, "ok"),
            (GREEN_FAIL, False, "!!"),
            (EXPECTED, True, ".."),
            (EXPECTED, False, "!!"),  # the run does not say it is in the Design stage
            (GREEN_FAIL, True, "!!"),  # the result is not one the runner excused
            (RED_PASS, True, "!!"),
        ]
        for result, before_implement, mark in cases:
            with self.subTest(result=result, before_implement=before_implement):
                self.assertEqual(testing.result_mark(result, before_implement=before_implement), mark)

    def test_the_exit_code(self):
        cases = [
            ({"results": [GREEN_PASS, RED_FAIL]}, {}, 0),
            ({"results": [GREEN_FAIL]}, {}, 1),
            ({"results": [EXPECTED], "before_implement": True}, {}, 0),
            ({"results": [GREEN_FAIL, EXPECTED], "before_implement": True}, {}, 1),  # one failure the runner did not excuse
            ({"results": [GREEN_PASS], "dirty_tree": True}, {}, 1),
            ({"results": [GREEN_PASS], "dirty_tree": True}, {"no_red": True}, 0),
            ({"results": [GREEN_PASS], "dirty_tree": True, "partial": True}, {}, 0),
            ({"results": []}, {}, 1),  # a full run that ran no command proves nothing
            ({"results": []}, {"no_red": True}, 1),
            ({"results": [], "before_implement": True}, {}, 1),  # the Design stage excuses a failing run, never an empty one
            ({"results": [], "partial": True}, {}, 0),  # a quick check that selected nothing is partial
            ({"results": [], "untested": True}, {}, 0),  # the config says no test covers the changed paths
            ({"results": [], "untested": True, "dirty_tree": True}, {}, 1),
            ({"results": [GREEN_FAIL], "untested": True}, {}, 1),
        ]
        for evidence, kwargs, code in cases:
            with self.subTest(evidence=evidence, kwargs=kwargs):
                self.assertEqual(testing.exit_code(evidence, **kwargs), code)


if __name__ == "__main__":
    unittest.main()
