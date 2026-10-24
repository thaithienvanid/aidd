"""`aidd metrics --flaky`: per test, how often it passed on a re-run after failing on the same head.

The fixture holds gate events as `aidd gate --events` writes them (event.schema.json):

- head A: the runner's retry passed `unit` after a failure (`flaky`); the gate ran twice on that head, which counts once
- head B: `unit` green at once
- head C: `unit` failed, then a re-run of the CI job on the same head passed it
- head D: `unit` failed and never passed: a red head, not a flake
- head E: `e2e` passed only on the runner's retry
- `lint` passed at once on every head
"""

import contextlib
import json
import unittest

from helpers import ROOT, run_cli

from aidd.tracking import metrics
from aidd.kernel import json_schema

FIXTURE = ROOT / "tests" / "fixtures" / "metrics" / "flaky-events.jsonl"


class FlakyTests(unittest.TestCase):
    def setUp(self):
        self.events = metrics.load_events([str(FIXTURE)])

    def test_the_fixture_is_real_gate_events(self):
        self.assertEqual(len(self.events), 7)
        for e in self.events:
            self.assertEqual(json_schema.validate(e, "event.schema.json"), [], e)

    def test_per_test_counts_by_head(self):
        out = metrics.flaky(self.events)
        self.assertEqual(out["schema_version"], metrics.METRICS_SCHEMA_VERSION)
        self.assertEqual(out["limit"], 0.05)
        rows = {r["name"]: r for r in out["tests"]}
        self.assertEqual(
            {n: (r["heads"], r["passed_on_rerun"], r["rate"], r["over_limit"]) for n, r in rows.items()},
            {"e2e": (1, 1, 1.0, True), "unit": (4, 2, 0.5, True), "lint": (5, 0, 0.0, False)},
        )
        # Worst first, so the test to fix first is on top.
        self.assertEqual([r["name"] for r in out["tests"]], ["e2e", "unit", "lint"])

    def test_a_late_pass_on_another_head_is_no_flake(self):
        # `unit` failed on D and passed on B: different heads, so neither is a re-run of the other.
        late = [e for e in self.events if e["head_sha"] in ("b" * 40, "d" * 40)]
        rows = {r["name"]: r for r in metrics.flaky(late)["tests"]}
        self.assertEqual((rows["unit"]["heads"], rows["unit"]["passed_on_rerun"]), (2, 0))

    def test_an_unknown_head_is_skipped(self):
        # The reviewer's case: `unit` failed on one event whose head the gate could not tell, then passed on another.
        # Two different commits may both have an empty head_sha, so neither is a re-run of the other.
        def ev(ts, status, flaky=False, head=""):
            t = {"name": "unit", "red_green": "green", "status": status} | ({"flaky": True} if flaky else {})
            return {"aidd_version": "1.0.0", "ts": ts, "repo": "o/r", "change": "9", "head_sha": head, "profile": "team", "decision": "pass", "tests": [t]}

        unknown = [ev("2026-09-01T09:00:00Z", "failed"), ev("2026-09-01T10:00:00Z", "passed")]
        for e in unknown:
            self.assertEqual(json_schema.validate(e, "event.schema.json"), [], e)
        self.assertEqual(metrics.flaky(unknown)["tests"], [])
        # The runner's own retry needs no head: it ran on one commit, so it counts as one flaky head.
        rows = metrics.flaky([*unknown, ev("2026-09-01T11:00:00Z", "passed", flaky=True)])["tests"]
        self.assertEqual([(r["heads"], r["passed_on_rerun"]) for r in rows], [(1, 1)])

    def test_only_a_failure_or_a_timeout_is_a_fail(self):
        def ev(ts, status):
            t = {"name": "unit", "red_green": "green", "status": status}
            return {"aidd_version": "1.0.0", "ts": ts, "repo": "o/r", "change": "9", "head_sha": "f" * 40, "profile": "team", "decision": "pass", "tests": [t]}

        for first, rerun in (("failed", 1), ("timeout", 1), ("not_started", 0), ("cancelled", 0)):
            rows = metrics.flaky([ev("2026-09-01T09:00:00Z", first), ev("2026-09-01T10:00:00Z", "passed")])["tests"]
            self.assertEqual([(r["heads"], r["passed_on_rerun"]) for r in rows], [(1, rerun)], first)

    def test_the_json_matches_its_schema(self):
        self.assertEqual(json_schema.validate(metrics.flaky(self.events), "metrics.schema.json#/$defs/flaky"), [])
        self.assertEqual(json_schema.validate(metrics.flaky(self.events), "metrics.schema.json"), [])
        self.assertTrue(json_schema.validate(metrics.flaky(self.events) | {"extra": 1}, "metrics.schema.json#/$defs/flaky"))
        self.assertEqual(json_schema.validate(metrics.flaky([]), "metrics.schema.json#/$defs/flaky"), [])

    def test_the_command(self):
        with contextlib.chdir(ROOT):
            code, out = run_cli("metrics", str(FIXTURE), "--flaky", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out), metrics.flaky(self.events))
        with contextlib.chdir(ROOT):
            code, out = run_cli("metrics", str(FIXTURE), "--flaky")
        self.assertEqual(code, 0, out)
        self.assertIn("| e2e | 1 | 1 | 100% | over the limit |", out)
        self.assertIn("| lint | 5 | 0 | 0% |  |", out)
        self.assertIn("5%", out)

    def test_it_goes_alone(self):
        for other in (["--by", "author"], ["--dora"], ["--autonomy"], ["--guard"], ["--target-wait", "60"]):
            with contextlib.chdir(ROOT):
                code, out = run_cli("metrics", str(FIXTURE), "--flaky", *other)
            self.assertEqual(code, 2, out)
            self.assertIn("--flaky", out)


if __name__ == "__main__":
    unittest.main()
