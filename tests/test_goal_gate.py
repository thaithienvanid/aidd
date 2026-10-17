"""A goal's change (`specs`): the gate judges each Spec as its own change against the whole diff (gate/engine.py)."""

from __future__ import annotations

import copy
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts src on sys.path)

from aidd import gate, workitems
from aidd.evals import examples

CASE = Path(__file__).resolve().parent.parent / "examples" / "23-goal-two-specs"
APPROVE = "/aidd " + "approve-spec"


def goal_context() -> dict:
    return examples.load_example(CASE)[0]


def with_proof(ctx: dict, spec_id: str, paths: list[str]) -> dict:
    """The context with `spec_id`'s approval naming a commit in head's history whose own diff is `paths`."""
    out = copy.deepcopy(ctx)
    sha = "c" * 40
    for c in out["comments"]:
        if f" {spec_id} " in c["body"]:
            c["body"] = c["body"].rstrip() + f" {sha}"
    out["approval_commits"] = {sha: {"ancestor": True, "paths": paths}}
    return out


def respec(ctx: dict, path: str, old: str, new: str) -> dict:
    """The context with the Spec at `path` edited, and its approval moved to the new hash."""
    out = copy.deepcopy(ctx)
    before = workitems.spec_hash(out["head_files"][path], out["head_tree"])
    out["head_files"][path] = out["head_files"][path].replace(old, new, 1)
    after = workitems.spec_hash(out["head_files"][path], out["head_tree"])
    for c in out["comments"]:
        c["body"] = c["body"].replace(before, after)
    return out


class GoalGateTests(unittest.TestCase):
    def test_each_spec_is_judged_and_recorded_on_its_own(self):
        d = gate.decide(goal_context())
        self.assertEqual(d.decision, "pass", d.codes())
        self.assertEqual([s["spec_id"] for s in d.record["specs"]], ["SPEC-220", "SPEC-222"])
        self.assertIsNone(d.record["spec"])
        self.assertTrue(all(s["spec_approved_by"] == ["checkout-lead"] for s in d.record["specs"]))

    def test_another_specs_code_is_not_this_ones_implementation(self):
        ctx = with_proof(goal_context(), "SPEC-222", ["specs/SPEC-222.md", "tests/checkout/test_totals.py", "src/checkout/rate_limit/limiter.py"])
        proofs = {s["spec_id"]: s["spec_approval_before_implementation"] for s in gate.decide(ctx).record["specs"]}
        self.assertTrue(proofs["SPEC-222"])  # SPEC-220's code was already there: SPEC-222's approval still came first

    def test_its_own_code_never_passes_for_the_goals_other_work(self):
        # SPEC-220's scope widens over all of checkout, so it also covers SPEC-222's own file: that file is still SPEC-222's.
        ctx = respec(goal_context(), "specs/SPEC-220.md", "scope: [src/checkout/rate_limit/]", "scope: [src/checkout/]")
        ctx = with_proof(ctx, "SPEC-222", ["specs/SPEC-222.md", "tests/checkout/test_totals.py", "src/checkout/totals.py"])
        d = gate.decide(ctx)
        proofs = {s["spec_id"]: s["spec_approval_before_implementation"] for s in d.record["specs"]}
        self.assertFalse(proofs["SPEC-222"])
        self.assertIn("warn spec_approval.after_implementation", d.codes())
        self.assertTrue(any(f.message.startswith("SPEC-222: ") for f in d.findings if f.code == "spec_approval.after_implementation"))

    def test_a_finding_every_spec_gives_is_reported_once(self):
        ctx = goal_context()
        ctx["reviews"] = []
        merge = [f for f in gate.decide(ctx).findings if f.rule == "merge_approval"]
        self.assertEqual(len(merge), 1)
        self.assertFalse(merge[0].message.startswith("SPEC-"))


if __name__ == "__main__":
    unittest.main()
