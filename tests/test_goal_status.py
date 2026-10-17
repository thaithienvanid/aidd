"""A goal's Spec integrates instead of waiting for a per-Spec Merge approval, and a goal says when it is old, behind, or
ready to release."""

from __future__ import annotations

import unittest

from helpers import ROOT  # noqa: F401  (puts src on the path)

from aidd import workitems
from aidd.autopilot import engine
from aidd.tracking import next_steps

SPEC = {"id": "SPEC-1", "kind": "spec", "route": "normal", "base": "goal/booking"}
HEAD = "a" * 40


def step(status: str, *, integrated: bool = False, data: dict = SPEC) -> dict:
    return next_steps._spec_step("specs/SPEC-1.md", data, status, committed=True, approval=True, blockers=[], local=True, integrated=integrated)


class GoalStepTests(unittest.TestCase):
    def test_a_built_goal_spec_integrates_with_no_person_asked(self):
        s = step("in_review")
        self.assertEqual((s["code"], s["who"]), ("spec.integrate", "agent"))
        self.assertIn("`aidd integrate`", s["how"])
        plain = step("in_review", data={k: v for k, v in SPEC.items() if k != "base"})
        self.assertEqual(plain["code"], "spec.in_review")  # off a goal, the person's Merge approval as before

    def test_an_integrated_spec_waits_for_the_goals_release(self):
        self.assertEqual(step("in_review", integrated=True)["code"], "spec.integrated")
        self.assertEqual(step("shipped", integrated=True)["code"], "spec.shipped")

    def test_autopilot_verifies_and_reviews_before_it_integrates(self):
        steps = [step("in_review") | {"id": "SPEC-1"}]
        base = {"steps": steps, "heads": {"SPEC-1": HEAD}, "cleared": {"SPEC-1"}}
        self.assertEqual(engine.resolve(steps[0], engine.Inputs(**base)), "spec.verify")
        verified = [{"spec": "SPEC-1", "code": "spec.verify", "result": "ok", "head": HEAD}]
        self.assertEqual(engine.resolve(steps[0], engine.Inputs(**base, journal=verified)), "spec.review")
        reviewed = verified + [{"spec": "SPEC-1", "code": "spec.review", "result": "ok", "head": HEAD}]
        self.assertEqual(engine.resolve(steps[0], engine.Inputs(**base, journal=reviewed)), "spec.integrate")
        self.assertEqual(engine.SHELL_STEPS["spec.integrate"], "aidd integrate")
        failed = verified + [{"spec": "SPEC-1", "code": "spec.review", "result": "fail", "head": HEAD}]
        self.assertEqual(engine.resolve(steps[0], engine.Inputs(**base, journal=failed)), "spec.rework")


class GoalWarningTests(unittest.TestCase):
    def facts(self, **kw) -> dict:
        return {"branch": "goal/booking", "head": HEAD, "age_days": 3, "behind": 0} | kw

    def test_a_goal_stays_short_and_close_to_the_default_branch(self):
        self.assertEqual(workitems.goal_warnings(self.facts(), 14), [])
        (old,) = workitems.goal_warnings(self.facts(age_days=20), 14)
        self.assertIn("past gates.max_goal_days = 14", old)
        self.assertEqual(workitems.goal_warnings(self.facts(age_days=20), 0), [])  # 0: off
        (behind,) = workitems.goal_warnings(self.facts(behind=4), 14)
        self.assertIn("`aidd sync`", behind)

    def test_the_limit_comes_from_the_config(self):
        class Cfg:
            def __init__(self, gates):
                self.gates = gates

        self.assertEqual(workitems.goal_limit(None), 7)
        self.assertEqual(workitems.goal_limit(Cfg({"max_goal_days": 5})), 5)
        self.assertEqual(workitems.goal_limit(Cfg({"max_goal_days": 0})), 0)


if __name__ == "__main__":
    unittest.main()
