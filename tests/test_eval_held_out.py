"""The held-out cases: about one case in five, fixed by its id and a seed, scored apart from the rest so no one tunes against them."""

import json
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT
from helpers import run_cli as run

from aidd import evals
from aidd.cli.commands import maintain
from aidd.evals import suites

# The shipped held-out cases, pinned. A rename moves a case in or out of the set without a word, because the set is picked by the id's
# hash. Change this list only in a change that says why: a new case lands here, and a case whose pass bar was edited leaves it for
# MOVED_TO_DEVELOPMENT in suites.py.
HELD_OUT_IDS = {
    "routing": [
        "c05-rbac",
        "c16-secret-rotation",
        "c18-gdpr-export",
        "c21-perf-threshold",
        "c28-crypto",
        "c33-api-field-rename",
        "c35-test-config",
        "c36-iam-terraform",
        "c38-emergency-workflow",
        "c48-deploy-config",
        "c52-firebase-config",
        "c60-demo-tomorrow-cli-flag",
    ],
    "roles": [
        "r01-reviewer-planted-bug",
        "r07-product-manager-scope-creep",
        "r08-product-designer-missing-states",
        "r12-tech-writer-generated-block",
        "r15-verifier-acceptance-mismatch",
        "r18-domain-expert-payments",
        "r24-domain-expert-games",
        "r29-reviewer-hardening-note",
        "r40-designer-state-copy",
        "r42-tech-writer-restate-first",
        "r71-verifier-ai-answers-unmeasured",
        "r72-architect-new-repository-no-stack",
        "r73-sre-year-end-freeze",
        "r74-domain-expert-kids-reading-app",
    ],
}

# With the seed in suites.py, s5 is held out and s1, s2, and s3 are not.
SCENARIOS = """
scenario:
  - id: s1
    situation: ROUTE=minor a typo
    expected: {route: minor}
  - id: s5
    situation: ROUTE=major an auth change
    expected: {route: major}
  - id: s2
    situation: ROUTE=normal a new endpoint
    expected: {route: stop}
"""
AGENT = """
import json, re, sys
print(json.dumps({"route": re.search(r"ROUTE=(\\w+)", sys.stdin.read()).group(1), "reason": "x"}))
"""


class SelectionTests(unittest.TestCase):
    def test_a_case_is_held_out_by_its_id_and_the_seed_alone(self):
        self.assertEqual([suites.is_held_out(x) for x in ("s1", "s2", "s3", "s5")], [False, False, False, True])
        self.assertEqual(suites.is_held_out("s5"), suites.is_held_out("s5"))
        names = [f"case-{n}" for n in range(60)]
        before = [suites.is_held_out(x) for x in names]
        with mock.patch.object(suites, "HELD_OUT_SEED", "another seed"):
            self.assertNotEqual([suites.is_held_out(x) for x in names], before, "the seed picks the set")

    def test_about_a_fifth_of_each_shipped_suite_is_held_out(self):
        for suite in ("routing", "roles"):
            with self.subTest(suite):
                ids = [sc["id"] for sc in evals.load_scenarios(ROOT / "evals" / suite)]
                share = sum(map(suites.is_held_out, ids)) / len(ids)
                self.assertTrue(0.10 <= share <= 0.30, f"{share:.0%} of the {suite} cases are held out; change HELD_OUT_SEED, which moves the set once")

    def test_the_held_out_cases_are_the_ones_pinned_here(self):
        for suite, want in HELD_OUT_IDS.items():
            with self.subTest(suite):
                got = [sc["id"] for sc in evals.load_scenarios(ROOT / "evals" / suite) if suites.is_held_out(sc["id"])]
                self.assertEqual(
                    got,
                    want,
                    "a case moved in or out of the held-out set. A renamed id moves it silently: restore the id. A held-out case whose pass bar you "
                    "edited belongs in MOVED_TO_DEVELOPMENT, with a new blind case written for the set",
                )

    def test_a_case_whose_bar_changed_after_the_split_is_development_whatever_its_hash(self):
        moved = suites.MOVED_TO_DEVELOPMENT
        shipped = {sc["id"] for suite in ("routing", "roles") for sc in evals.load_scenarios(ROOT / "evals" / suite)}
        self.assertTrue(moved <= shipped, "a moved id names no case: it was renamed or removed")
        with mock.patch.object(suites, "MOVED_TO_DEVELOPMENT", frozenset()):
            by_hash = {x for x in moved if suites.is_held_out(x)}
        self.assertEqual(
            by_hash,
            {
                "r52-compliance-dpia-pressure",
                "r53-compliance-review-controls",
                "r54-compliance-evidence-map",
                "r70-developer-plan-matches-the-diff",
                "c58-auth-library-privacy",
            },
        )
        self.assertFalse(any(suites.is_held_out(x) for x in moved))

    def test_adding_a_case_moves_no_other(self):
        ids = [f"case-{n}" for n in range(200)]
        before = {x: suites.is_held_out(x) for x in ids}
        after = {x: suites.is_held_out(x) for x in [*ids, "a-new-case"]}
        self.assertEqual({x: after[x] for x in ids}, before)
        self.assertTrue(0.10 <= sum(before.values()) / len(ids) <= 0.30)


class ScoreTests(unittest.TestCase):
    def test_the_two_sets_are_scored_apart(self):
        def row(pass_at_1, held_out):
            return {"id": "x", "pass_at_1": pass_at_1, "pass_all": pass_at_1 == 1, "held_out": held_out}

        cases = {
            "both sets": ([row(1.0, False), row(0.0, False), row(1.0, True)], (2, 0.5, 0.5), (1, 1.0, 1.0)),
            "only development": ([row(1.0, False)], (1, 1.0, 1.0), None),
            "only held out": ([row(0.5, True)], None, (1, 0.5, 0.0)),
            "nothing": ([], None, None),
        }
        for name, (results, dev, held) in cases.items():
            with self.subTest(name):
                got = suites.split_summary(results)
                for key, want in (("development", dev), ("held_out", held)):
                    self.assertEqual(None if got[key] is None else (got[key]["scenarios"], got[key]["mean_pass_at_1"], got[key]["pass_k_share"]), want)

    def test_measure_marks_each_result_by_its_id(self):
        results = suites.measure(lambda: [{"id": "s1", "ok": True}, {"id": "s5", "ok": True}], 1)
        self.assertEqual([(r["id"], r["held_out"]) for r in results], [("s1", False), ("s5", True)])


class SetsLineTests(unittest.TestCase):
    def test_a_held_out_set_under_the_compare_minimum_says_it_is_too_few(self):
        for n, too_few in ((1, True), (9, True), (10, False), (12, False)):
            with self.subTest(n):
                sets = {"development": None, "held_out": {"scenarios": n, "mean_pass_at_1": 1.0, "pass_k_share": 1.0}}
                self.assertEqual("too few to compare" in maintain._sets_line(sets, "pass@1"), too_few)


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        (base / "routing").mkdir()
        (base / "routing" / "scenarios.yaml").write_text(SCENARIOS, encoding="utf-8")
        (base / "agent.py").write_text(AGENT, encoding="utf-8")
        self.cmd = shlex.join([sys.executable, str(base / "agent.py")])
        self.record = base / "runs.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def routing(self, *extra: str) -> tuple[str, dict]:
        self.record.unlink(missing_ok=True)
        argv = [
            "routing",
            "--scenarios",
            str(Path(self.tmp.name) / "routing"),
            "--agent-command",
            self.cmd,
            "--min-accuracy",
            "0",
            "--record",
            str(self.record),
        ]
        code, out = run("eval", *argv, *extra)
        self.assertEqual(code, 0, out)
        (line,) = [json.loads(x) for x in self.record.read_text(encoding="utf-8").splitlines()]
        return out, line

    def test_the_run_prints_and_records_both_sets(self):
        out, line = self.routing()
        self.assertIn("development: pass@1 50.0% over 2; held-out: pass@1 100.0% over 1 (too few to compare: under 10 cases)", out)
        self.assertEqual(line["sets"]["development"]["mean_pass_at_1"], 0.5)
        self.assertEqual(line["sets"]["held_out"], {"scenarios": 1, "mean_pass_at_1": 1.0, "pass_k_share": 1.0})
        self.assertEqual({s["id"]: s.get("held_out", False) for s in line["scenarios"]}, {"s1": False, "s5": True, "s2": False})

    def test_a_set_with_no_case_in_the_run_says_so(self):
        out, line = self.routing("--case", "s5")
        self.assertIn("development: no case; held-out: pass@1 100.0% over 1", out)
        self.assertIsNone(line["sets"]["development"])
        out, _ = self.routing("--case", "s1", "--repeat", "2")
        self.assertIn("development: mean pass@1 100.0% over 1; held-out: no case", out)


if __name__ == "__main__":
    unittest.main()
