"""Loop speed, cost, and autonomy proposals in `aidd metrics`: what the events support, each paired with a quality metric."""

import contextlib
import json
import tempfile
import unittest
from pathlib import Path

from helpers import decide, example, run_cli

from aidd.tracking import metrics
from aidd.gate import decision_report
from aidd.setup import adoption
from aidd.kernel import documents, json_schema


def ev(change, ts, decision="pending", head="a" * 40, **kw):
    base = {"repo": "o/r", "change": change, "ts": ts, "head_sha": head, "decision": decision, "pending_rules": [], "failed_rules": [], "route": "normal"}
    return base | kw


H1, H2 = "1" * 40, "2" * 40

# Change 1: opened at 09:00, first head pushed 09:00, tests reported at 09:20 (20 min to feedback); Spec approval pending
# 09:20 to 10:20; a fix-up head pushed 10:30, tests reported 10:35 (5 min); Merge approval pending 10:35 to 11:00; pass.
CHANGE_1 = [
    ev("1", "2026-09-01T09:05:00Z", head=H1, pending_rules=["tests", "spec_approval"], opened_at="2026-09-01T09:00:00Z", head_pushed_at="2026-09-01T09:00:00Z"),
    ev(
        "1",
        "2026-09-01T09:20:00Z",
        head=H1,
        pending_rules=["spec_approval"],
        head_pushed_at="2026-09-01T09:00:00Z",
        spec_hash="x",
        spec="specs/SPEC-7.md",
        spec_id="SPEC-7",
    ),
    ev("1", "2026-09-01T10:20:00Z", head=H1, decision="fail", failed_rules=["tests"], spec_hash="x", spec="specs/SPEC-7.md", spec_id="SPEC-7"),
    ev("1", "2026-09-01T10:35:00Z", head=H2, pending_rules=["merge_approval"], head_pushed_at="2026-09-01T10:30:00Z", spec_hash="x", spec_id="SPEC-7"),
    ev("1", "2026-09-01T11:00:00Z", head=H2, decision="pass", head_pushed_at="2026-09-01T10:30:00Z", spec_hash="x", spec_id="SPEC-7"),
]


class EventFieldTests(unittest.TestCase):
    def test_the_event_carries_the_opening_the_push_the_spec_id_and_its_version(self):
        ctx = example("02-normal-feature")
        ctx["change"]["created_at"] = "2026-09-22T08:00:00Z"
        ctx["head_pushed_at"] = "2026-09-23T09:00:00Z"
        d = decide(ctx)
        line = decision_report.decision_event(d, "acme/shop")
        self.assertEqual(json_schema.validate(line, "event.schema.json"), [])
        self.assertEqual((line["opened_at"], line["head_pushed_at"]), ("2026-09-22T08:00:00Z", "2026-09-23T09:00:00Z"))
        self.assertEqual(line["spec_id"], d.record.get("spec_id"))
        self.assertIsNotNone(line["spec_id"])
        self.assertEqual(line["schema_version"], decision_report.EVENT_SCHEMA_VERSION)
        # The timing never reaches the record: it is a fact for metrics, not for a rule.
        self.assertNotIn("opened_at", d.record)
        self.assertNotIn("head_pushed_at", d.record)

    def test_without_the_times_the_fields_are_null_and_the_error_line_is_versioned(self):
        line = decision_report.decision_event(decide(example("02-normal-feature")), "acme/shop")
        self.assertEqual((line["opened_at"], line["head_pushed_at"]), (None, None))
        err = decision_report.error_event("o/r", "1", RuntimeError("x"))
        self.assertEqual(json_schema.validate(err, "event.schema.json"), [])
        self.assertEqual(err["schema_version"], "1")

    def test_old_lines_without_the_new_fields_still_validate_and_summarize(self):
        old = {"aidd_version": "1.0.0", "ts": "2026-09-01T09:00:00Z", "change": "1", "head_sha": "", "profile": "team", "decision": "pass"}
        self.assertEqual(json_schema.validate(old, "event.schema.json"), [])
        s = metrics.summarize_events([old])
        self.assertIsNone(s["first_feedback_minutes"])
        self.assertIsNone(s["flow_efficiency"])


class LoopSpeedTests(unittest.TestCase):
    def test_time_to_first_feedback_is_per_head_from_its_push_to_its_first_test_result(self):
        self.assertEqual(metrics.first_feedback(CHANGE_1), [20.0, 5.0])
        s = metrics.summarize_events(CHANGE_1)
        self.assertEqual(s["first_feedback_minutes"], {"p50": 12.5, "p90": 20.0, "samples": 2})

    def test_the_opening_stands_in_for_the_first_heads_push(self):
        events = [ev("1", "2026-09-01T09:30:00Z", opened_at="2026-09-01T09:00:00Z")]
        self.assertEqual(metrics.first_feedback(events), [30.0])
        # A later head without a push time gives no sample: the events cannot say when it started.
        events.append(ev("1", "2026-09-01T10:00:00Z", head=H2))
        self.assertEqual(metrics.first_feedback(events), [30.0])

    def test_approval_waits_are_per_approval_with_p50_and_p90(self):
        s = metrics.summarize_events(CHANGE_1)
        self.assertEqual(
            s["approval_wait_minutes"],
            {
                "spec_approval": {"name": "Spec approval", "p50": 75.0, "p90": 75.0, "samples": 1},
                "merge_approval": {"name": "Merge approval", "p50": 25.0, "p90": 25.0, "samples": 1},
            },
        )
        self.assertNotIn("tests", s["approval_wait_minutes"])

    def test_percentiles_are_nearest_rank(self):
        values = [float(v) for v in range(1, 11)]
        self.assertEqual(metrics.percentile(values, 0.9), 9.0)
        self.assertEqual(metrics.percentile([5.0], 0.9), 5.0)
        self.assertIsNone(metrics.percentile([], 0.9))
        self.assertEqual(metrics.spread(values), {"p50": 5.5, "p90": 9.0, "samples": 10})

    def test_flow_efficiency_is_lead_time_not_spent_waiting_on_an_approval(self):
        # Lead 09:00 (opened) to 11:00 = 120 min; waiting on an approval: 09:05-10:20 (75) and 10:35-11:00 (25).
        self.assertEqual(metrics.flow(CHANGE_1), (120.0, 20.0))
        self.assertEqual(metrics.summarize_events(CHANGE_1)["flow_efficiency"], round(20 / 120, 3))
        # A change that never passed has no lead time yet.
        self.assertIsNone(metrics.flow(CHANGE_1[:3]))

    def test_rework_rate_counts_only_specs_that_were_approved(self):
        reworked = [*CHANGE_1, ev("1", "2026-09-01T12:00:00Z", head=H2, spec_hash="y", spec_id="SPEC-7")]
        self.assertEqual(metrics.summarize_events(reworked)["spec_rework_rate"], 1.0)
        self.assertEqual(metrics.summarize_events(CHANGE_1)["spec_rework_rate"], 0.0)
        self.assertIsNone(metrics.summarize_events([ev("2", "2026-09-01T09:00:00Z")])["spec_rework_rate"])

    def test_fast_merge_approvals_on_major_changes_are_named(self):
        """The rubber-stamp indicator: a major change whose Merge approval wait ended within 10 minutes of the gate
        first asking for it. Normal changes, and waits still open, are not counted."""

        def change(n, minutes, route="major"):
            return [
                ev(n, "2026-09-01T10:00:00Z", pending_rules=["merge_approval"], route=route),
                ev(n, f"2026-09-01T10:{minutes:02d}:00Z", decision="pass", route=route),
            ]

        events = (
            change("1", 3)
            + change("2", 45)
            + change("3", 2, route="normal")
            + [ev("4", "2026-09-01T10:00:00Z", pending_rules=["merge_approval"], route="major")]
        )
        s = metrics.summarize_events(events)
        self.assertEqual(s["fast_major_merge_approvals"], {"within_minutes": 10, "count": 1, "of": 2, "changes": ["o/r#1"]})
        self.assertEqual(json_schema.validate(s, "metrics.schema.json#/$defs/summary"), [])
        self.assertIn("| Major changes merge-approved within 10 minutes (look again) | 1 of 2: o/r#1 |", metrics.metrics_markdown(s))
        self.assertIsNone(metrics.summarize_events(change("5", 2, route="normal"))["fast_major_merge_approvals"])

    def test_each_speed_metric_is_paired_with_a_quality_metric_and_judged_against_its_target(self):
        s = metrics.summarize_events(CHANGE_1, targets={"max_first_feedback_minutes": 10, "max_approval_wait_p90_minutes": 120, "min_flow_efficiency": 0.5})
        rows = {r["metric"]: r for r in s["loop_speed"]}
        self.assertEqual(set(rows), {"first_feedback_minutes", "approval_wait_p90_minutes", "flow_efficiency"})  # the measures; the targets carry max_ or min_
        self.assertEqual((rows["first_feedback_minutes"]["value"], rows["first_feedback_minutes"]["met"]), (12.5, False))
        self.assertEqual((rows["approval_wait_p90_minutes"]["value"], rows["approval_wait_p90_minutes"]["met"]), (75.0, True))
        self.assertEqual(rows["flow_efficiency"]["met"], False)
        for r in rows.values():
            self.assertIn(r["paired_with"]["metric"], s)
            self.assertEqual(r["paired_with"]["value"], s[r["paired_with"]["metric"]])
        text = metrics.metrics_markdown(s)
        self.assertIn("| Time to first feedback (p50, minutes) | 12.5 | ≤ 10 | **no** | First-pass test rate |", text)
        self.assertNotRegex(text, r"(per|by) gate|Gates above")


class CliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.events = self.root / "events.jsonl"
        self.events.write_text("".join(json.dumps(e) + "\n" for e in CHANGE_1), encoding="utf-8")

    def targets(self, **values):
        cfg = self.root / ".aidd" / "config.yaml"
        if not cfg.is_file():
            adoption.init(self.root, adoption.InitOptions(profile="team", ci="none", links=[], skill=False, approvers=["@lead"], harnesses=[]))
            self.base = cfg.read_text(encoding="utf-8")
        cfg.write_text(self.base + ("\ntargets:\n" + "".join(f"  {k}: {v}\n" for k, v in values.items()) if values else ""), encoding="utf-8")

    def metrics(self, *args):
        with contextlib.chdir(self.root):
            return run_cli("metrics", str(self.events), *args)

    def test_no_targets_exits_0_and_json_is_versioned(self):
        code, out = self.metrics("--json")
        self.assertEqual(code, 0, out)
        s = json.loads(out)
        self.assertEqual(s["schema_version"], metrics.METRICS_SCHEMA_VERSION)
        self.assertTrue(all(r["met"] is None for r in s["loop_speed"]))

    def test_a_missed_loop_speed_target_exits_1_and_a_met_one_exits_0(self):
        self.targets(max_first_feedback_minutes=10)
        code, out = self.metrics()
        self.assertEqual(code, 1, out)
        self.targets(max_first_feedback_minutes=15, max_approval_wait_p90_minutes=90, min_flow_efficiency=0.1)
        self.assertEqual(self.metrics()[0], 0)
        self.targets(min_flow_efficiency=0.9)
        self.assertEqual(self.metrics()[0], 1)

    def test_the_new_targets_are_valid_config(self):
        self.targets(
            max_first_feedback_minutes=30, max_approval_wait_p90_minutes=1440, min_flow_efficiency=0.4, max_cost_per_change="{amount: 5, currency: USD}"
        )
        with contextlib.chdir(self.root):
            code, out = run_cli("validate", ".aidd/config.yaml")
        self.assertEqual(code, 0, out)

    def cost_log(self, *lines):
        path = self.root / "cost.jsonl"
        path.write_text("".join((json.dumps(x) if isinstance(x, dict) else x) + "\n" for x in lines), encoding="utf-8")
        return str(path)

    def test_cost_joins_by_spec_sha_and_branch_and_never_sets_the_exit_code(self):
        other = [ev("feat/login", "2026-09-02T09:00:00Z", head="3" * 40, decision="pass")]
        with self.events.open("a", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(e) + "\n" for e in other))
        path = self.cost_log(
            {"ts": "2026-09-01T09:10:00Z", "amount": 3.0, "currency": "USD", "agent": "claude-code/claude-opus-5-5", "spec": "SPEC-7"},
            {"ts": "2026-09-01T10:31:00Z", "amount": 1.0, "currency": "USD", "sha": H2[:12]},
            {"ts": "2026-09-02T09:00:00Z", "amount": 2.0, "currency": "USD", "branch": "feat/login"},
            {"ts": "2026-09-02T09:00:00Z", "amount": 9.0, "currency": "USD", "branch": "nowhere"},
        )
        self.targets(max_cost_per_change="{amount: 2.5, currency: USD}")
        code, out = self.metrics("--cost", path, "--json")
        self.assertEqual(code, 0, out)  # a missed cost target is shown, never enforced
        c = json.loads(out[out.index("{") :])["cost"]
        self.assertEqual(c["joined_by"], {"branch": 1, "none": 1, "sha": 1, "spec": 1})
        self.assertEqual(c["currencies"]["USD"], {"total": 6.0, "changes": 2, "per_change": 3.0, "median_per_change": 3.0})
        self.assertEqual(c["unattributed"], {"USD": 9.0})
        self.assertEqual((c["cap"], c["met"], c["display_only"]), ({"amount": 2.5, "currency": "USD"}, False, True))
        self.assertEqual([o["amount"] for o in c["over_cap"]], [4.0])  # SPEC-7's 3 and its head's 1; feat/login's 2 is within it
        self.assertEqual(c["paired_with"]["metric"], "first_pass_share")
        code, text = self.metrics("--cost", path)
        self.assertIn("Cost per change (USD) | 3.0 over 2 changes", text)
        self.assertIn("never enforced", text)

    def test_a_change_over_the_cost_cap_is_a_warning_never_an_exit_code(self):
        other = [ev("feat/login", "2026-09-02T09:00:00Z", head="3" * 40, decision="pass")]
        with self.events.open("a", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(e) + "\n" for e in other))
        path = self.cost_log(
            {"ts": "2026-09-01T09:10:00Z", "amount": 7.5, "currency": "USD", "spec": "SPEC-7"},
            {"ts": "2026-09-01T09:10:00Z", "amount": 90, "currency": "EUR", "spec": "SPEC-7"},  # another currency: never converted
            {"ts": "2026-09-02T09:00:00Z", "amount": 2.0, "currency": "USD", "branch": "feat/login"},
        )
        self.targets(max_cost_per_change="{amount: 5, currency: USD}")
        code, out = self.metrics("--cost", path, "--json")
        self.assertEqual(code, 0, out)
        c = json.loads(out[out.index("{") :])
        self.assertEqual(c["cost"]["cap"], {"amount": 5, "currency": "USD"})
        self.assertEqual(c["cost"]["over_cap"], [{"change": "o/r#1", "amount": 7.5, "currency": "USD"}])
        self.assertEqual(json_schema.validate(c, "metrics.schema.json"), [])
        code, text = self.metrics("--cost", path)
        self.assertEqual(code, 0, text)
        self.assertIn("warning: change o/r#1 cost 7.5 USD, over `targets.max_cost_per_change` (5 USD)", text)
        self.assertIn("| Target cost per change | ≤ 5 USD: **no** |", text)
        self.assertIn("| Over the cap (5 USD) | o/r#1: 7.5 |", text)
        # Without a cap there is nothing to be over, or to meet; the config refuses a cap without its currency.
        self.targets()
        c = json.loads(self.metrics("--cost", path, "--json")[1])
        self.assertEqual((c["cost"]["cap"], c["cost"]["over_cap"], c["cost"]["met"]), (None, [], None))
        self.targets(max_cost_per_change="{amount: 5}")
        with contextlib.chdir(self.root):
            self.assertNotEqual(run_cli("validate", ".aidd/config.yaml")[0], 0)

    def test_a_spec_shared_by_two_changes_splits_its_cost_and_currencies_are_never_converted(self):
        two = [ev("2", "2026-09-03T09:00:00Z", head="4" * 40, decision="pass", spec_id="SPEC-7")]
        with self.events.open("a", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(e) + "\n" for e in two))
        path = self.cost_log(
            {"ts": "2026-09-01T09:10:00Z", "amount": 4, "currency": "USD", "spec": "SPEC-7"},
            {"ts": "2026-09-01T09:10:00Z", "amount": 1, "currency": "EUR", "spec": "SPEC-7"},
        )
        with contextlib.chdir(self.root):
            c = metrics.cost_per_change(
                metrics.load_events([str(self.events)]), metrics.load_cost_log(path), {"max_cost_per_change": {"amount": 1, "currency": "EUR"}}
            )
        self.assertEqual(c["currencies"]["USD"]["per_change"], 2.0)
        self.assertEqual(c["currencies"]["EUR"]["per_change"], 0.5)
        self.assertTrue(c["met"])  # only the cap's currency counts: aidd converts nothing, so the USD is never judged

    def test_a_malformed_cost_log_line_is_an_error_naming_it(self):
        for bad in (
            "not json",
            {"ts": "2026-09-01", "amount": "3", "currency": "USD"},
            {"ts": "yesterday", "amount": 3, "currency": "USD"},
            {"ts": "2026-09-01", "amount": 3},
        ):
            path = self.cost_log({"ts": "2026-09-01T00:00:00Z", "amount": 1, "currency": "USD"}, bad)
            code, out = self.metrics("--cost", path)
            self.assertEqual(code, 2, out)
            self.assertIn("cost.jsonl:2:", out)

    def test_since_filters_the_cost_log_too(self):
        path = self.cost_log(
            {"ts": "2026-08-01T00:00:00Z", "amount": 50, "currency": "USD", "spec": "SPEC-7"},
            {"ts": "2026-09-01T09:10:00Z", "amount": 1, "currency": "USD", "spec": "SPEC-7"},
        )
        code, out = self.metrics("--cost", path, "--since", "2026-09-01", "--json")
        self.assertEqual(json.loads(out)["cost"]["currencies"]["USD"]["total"], 1.0)

    def test_cost_is_only_for_the_summary_and_propose_only_with_autonomy(self):
        self.assertEqual(self.metrics("--dora", "--cost", "x.jsonl")[0], 2)
        self.assertEqual(self.metrics("--suggest-standard-changes")[0], 2)


class ProposeTests(unittest.TestCase):
    AGENT = "claude-code/claude-opus-5-5"

    def events(self, n, *, failed=0):
        out = []
        for i in range(n):
            decision = "fail" if i < failed else "pass"
            out.append(
                ev(
                    str(i),
                    f"2026-09-01T09:{i % 60:02d}:00Z",
                    head=f"{i:040x}",
                    decision=decision,
                    assisted_by=[self.AGENT],
                    type="deps",
                    author="renovate[bot]",
                    changed_lines=10 + i,
                )
            )
        return out

    def test_a_class_that_meets_the_thresholds_gets_a_standard_change_entry_with_its_evidence(self):
        events = self.events(25)
        rows = metrics.autonomy(events)
        proposals = metrics.propose_standard_changes(events, rows, ["deps"])
        self.assertEqual(len(proposals), 1)
        p = proposals[0]
        self.assertEqual(p["evidence"], {"changes": 25, "passed": 25, "first_pass_share": 1.0, "failed": 0, "reworked": 0})
        self.assertIn(".aidd/** is a protected path", p["yaml"])
        self.assertIn("A person merges this", p["yaml"])
        entry = documents.parse_yaml(p["yaml"], "proposal")["standard_changes"][0]
        self.assertEqual(entry["authors"], ["renovate[bot]"])
        self.assertEqual((entry["type"], entry["max_changed_lines"], entry["paths"]), ("deps", 34, []))
        # Empty paths fail the config schema, so an unfilled proposal can never merge as a working class.
        self.assertTrue(json_schema.validate({"standard_changes": [entry]}, "config.schema.json"))

    def test_a_class_below_the_thresholds_or_with_a_failure_gets_nothing(self):
        self.assertEqual(metrics.propose_standard_changes(self.events(24), metrics.autonomy(self.events(24))), [])
        failing = self.events(30, failed=1)
        self.assertEqual(metrics.propose_standard_changes(failing, metrics.autonomy(failing)), [])

    def test_the_command(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "events.jsonl"
            path.write_text("".join(json.dumps(e) + "\n" for e in self.events(25)), encoding="utf-8")
            with contextlib.chdir(d):
                code, out = run_cli("metrics", str(path), "--autonomy", "--suggest-standard-changes")
                self.assertEqual(code, 0, out)
                self.assertIn("standard_changes:", out)
                code, out = run_cli("metrics", str(path), "--autonomy", "--suggest-standard-changes", "--json")
                data = json.loads(out)
                self.assertEqual(data["schema_version"], metrics.METRICS_SCHEMA_VERSION)
                self.assertEqual(len(data["proposals"]), 1)
            path.write_text(json.dumps(self.events(1)[0]) + "\n", encoding="utf-8")
            with contextlib.chdir(d):
                code, out = run_cli("metrics", str(path), "--autonomy", "--suggest-standard-changes")
            self.assertEqual(code, 0, out)
            self.assertIn("nothing to suggest", out)


if __name__ == "__main__":
    unittest.main()
