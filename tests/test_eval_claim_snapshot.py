"""TEMPORARY, for the eval suite's migration (N1 to N11 of the 1.0.0 plan): no claim loses a case it had before the claims moved.

tests/eval_claim_snapshot.json holds each claim and the cases that proved it at commit 5a834252, before the registry. This
test fails when a case leaves a claim without a line in MOVED saying where it went and why. Delete this file and the fixture when
the migration ends (N9, the cases that belong elsewhere), because after that the registry and the coverage test hold the claims.
"""

import json
import unittest

from helpers import ROOT

from aidd import evals

SNAPSHOT = json.loads((ROOT / "tests" / "eval_claim_snapshot.json").read_text(encoding="utf-8"))["claims"]

# A claim renamed in the registry: the old name, then the new one. Every case of the old claim must now carry the new one.
RENAMED = {
    "duty:role-loads-its-practice-skill": "duty:developer.loads-its-practice-skill",  # a duty names its role
    "route:minor-profiler": "route:normal-profiler-not-personal",  # its case expects normal, so the name said the wrong route
}
# A case that stopped proving a claim, as (claim, case): it proves the claim in the value instead.
MOVED = {
    ("action:pr.merge", "team/delegate-approves-a-green-local-merge"): "action:git.merge",  # a local merge is git.merge, not pr.merge
}


def covered() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for row in evals.suite_cases(ROOT):
        for claim in row["claims"]:
            out.setdefault(claim, set()).add(f"{row['suite']}/{row['id']}")
    return out


class ClaimSnapshotTests(unittest.TestCase):
    def test_no_claim_lost_a_case_it_had(self):
        now = covered()
        lost = []
        for claim, cases in SNAPSHOT.items():
            target = RENAMED.get(claim, claim)
            for case in cases:
                moved = MOVED.get((claim, case))
                if case not in now.get(moved or target, set()):
                    lost.append(f"{case} no longer proves {claim}" + (f" (nor {moved})" if moved else ""))
        self.assertEqual(lost, [], "a case that moved to another claim is listed in MOVED with its reason")

    def test_each_move_and_rename_names_a_claim_and_a_case_that_the_snapshot_holds(self):
        for old, new in RENAMED.items():
            self.assertIn(old, SNAPSHOT)
            self.assertNotIn(old, covered(), "the old name is gone")
            self.assertIn(new, covered())
        for (claim, case), new in MOVED.items():
            self.assertIn(case, SNAPSHOT[claim])
            self.assertNotIn(case, covered().get(claim, set()))
            self.assertIn(case, covered()[new])


if __name__ == "__main__":
    unittest.main()
