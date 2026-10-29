"""The five DORA software delivery metrics from aidd's own records, against the targets a team sets for itself."""

import tempfile
import unittest
from pathlib import Path

from helpers import run_cli

from aidd.tracking import metrics


def ev(change, ts, decision="pass", route="normal"):
    return {"repo": "o/r", "change": change, "ts": ts, "decision": decision, "route": route, "pending_rules": [], "failed_rules": []}


EVENTS = [
    ev("1", "2026-09-01T09:00:00Z", "pending"),
    ev("1", "2026-09-01T13:00:00Z"),
    ev("2", "2026-09-02T09:00:00Z", "pending"),
    ev("2", "2026-09-03T09:00:00Z"),
    ev("3", "2026-09-10T09:00:00Z", "fail"),
    ev("4", "2026-09-15T09:00:00Z", "pending", "emergency"),
    ev("4", "2026-09-15T10:00:00Z", "pass", "emergency"),
]
SPEC = '---\naidd_version: "1.0.0"\nkind: spec\nid: "S-{n}"\nstatus: "{status}"\noutcome:\n  released_on: "2026-09-0{n}"\n{extra}---\n'


class DoraTests(unittest.TestCase):
    def rows(self, specs=None, targets=None):
        return {r["metric"]: r for r in metrics.dora(EVENTS, specs, targets)}

    def test_throughput_from_the_gate_events(self):
        r = self.rows()
        self.assertEqual(r["deployments_per_week"]["value"], 1.5)  # three passed changes over two weeks
        self.assertEqual(r["lead_time_hours"]["value"], 4.0)  # the median of 4, 24, and 1 hours
        self.assertEqual(r["rework_rate"]["value"], 0.333)  # one of three passed changes was an emergency
        self.assertIsNone(r["change_fail_rate"]["value"])  # stability needs the Specs' outcomes

    def test_stability_from_the_specs_outcomes(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "S-1.md").write_text(SPEC.format(n=1, status="done", extra=""), encoding="utf-8")
            Path(d, "S-2.md").write_text(SPEC.format(n=2, status="rolled_back", extra='  rolled_back: true\n  restored_on: "2026-09-04"\n'), encoding="utf-8")
            r = self.rows(Path(d))
            self.assertEqual(r["change_fail_rate"]["value"], 0.5)
            self.assertEqual(r["recovery_days"]["value"], 2)

    def test_each_metric_against_the_teams_own_target(self):
        r = self.rows(targets={"min_deployments_per_week": 2, "max_lead_time_hours": 8, "max_rework_rate": 0.5})
        self.assertIs(r["deployments_per_week"]["met"], False)  # higher is better
        self.assertIs(r["lead_time_hours"]["met"], True)  # lower is better
        self.assertIs(r["rework_rate"]["met"], True)
        self.assertIsNone(r["change_fail_rate"]["met"])  # no value, so no verdict
        text = metrics.dora_markdown(list(r.values()))
        self.assertIn("| Deployment frequency | 1.5 | ≥ 2 | **no** |", text)
        self.assertIn("not with other teams", text)

    def test_dora_and_the_summary_share_one_window(self):
        events = [ev("1", "2026-09-01T09:00:00Z"), ev("2", "2026-09-04T09:00:00Z")]  # two passes in three days
        dora = {r["metric"]: r for r in metrics.dora(events)}["deployments_per_week"]["value"]
        self.assertEqual(dora, metrics.summarize_events(events)["throughput_per_week"])
        self.assertEqual(dora, round(2 / (3 / 7), 2))

    def test_an_unreadable_since_is_an_error_not_a_silent_no_op(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "events.jsonl"
            f.write_text('{"ts": "2026-09-01T00:00:00Z"}\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                metrics.load_events([str(f)], since="last tuesday")
            code, out = run_cli("metrics", str(f), "--since", "last tuesday")
            self.assertEqual(code, 2)
            self.assertIn("--since 'last tuesday' is not an ISO date or time", out)

    def test_events_are_ordered_by_instant_not_by_text(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "events.jsonl"
            # As text, "…T01:00:00+02:00" sorts after "…T00:30:00Z"; as instants it is 23:00 the day before.
            f.write_text('{"ts": "2026-09-20T00:30:00Z"}\n{"ts": "2026-09-20T01:00:00+02:00"}\n', encoding="utf-8")
            self.assertEqual([e["ts"] for e in metrics.load_events([str(f)])], ["2026-09-20T01:00:00+02:00", "2026-09-20T00:30:00Z"])


if __name__ == "__main__":
    unittest.main()
