"""The stage metrics `aidd metrics` derives from gate events: speed to review, first-pass delivery, rework, and plan adherence."""

import unittest

from helpers import ROOT  # noqa: F401  (puts src on sys.path)

from aidd import metrics


def ev(ts, head="h1", **kw):
    base = {
        "aidd_version": "1.0.0",
        "ts": ts,
        "repo": "o/r",
        "change": "1",
        "head_sha": head,
        "profile": "team",
        "decision": "pending",
        "pending_rules": [],
        "failed_rules": [],
        "approvals": 0,
        "spec": "specs/S.md",
        "spec_hash": "a",
        "untouched_tasks": 0,
    }
    return base | kw


class StageMetricTests(unittest.TestCase):
    def test_hours_to_first_approval(self):
        s = metrics.summarize([ev("2026-09-28T08:00:00Z", pending_rules=["merge_approval"]), ev("2026-09-28T10:00:00Z", approvals=1, decision="pass")])
        self.assertEqual(s["median_hours_to_first_approval"], 2.0)

    def test_first_pass_means_the_tested_head_is_the_head_that_passed(self):
        clean = [ev("2026-09-28T08:00:00Z"), ev("2026-09-28T09:00:00Z", decision="pass")]
        fixup = [ev("2026-09-28T08:00:00Z", failed_rules=["tests"]), ev("2026-09-28T09:00:00Z", head="h2", decision="pass")]
        self.assertEqual(metrics.summarize(clean)["first_pass_share"], 1.0)
        self.assertEqual(metrics.summarize(fixup)["first_pass_share"], 0.0)

    def test_a_new_spec_hash_after_g1_counts_as_rework(self):
        before = ev("2026-09-28T07:00:00Z", pending_rules=["spec_approval"])
        approved = ev("2026-09-28T08:00:00Z")
        reworked = ev("2026-09-28T09:00:00Z", spec_hash="b", pending_rules=["spec_approval"])
        self.assertEqual(metrics.summarize([before, approved, reworked])["spec_reworked_after_g1"], 1)
        self.assertEqual(metrics.summarize([before, approved])["spec_reworked_after_g1"], 0)
        self.assertEqual(metrics.summarize([before])["spec_reworked_after_g1"], 0)  # never approved: not rework

    def test_plan_adherence_counts_specs_without_idle_tasks(self):
        s = metrics.summarize([ev("2026-09-28T08:00:00Z", untouched_tasks=1), ev("2026-09-28T08:00:00Z", change="2", untouched_tasks=0)])
        self.assertEqual(s["plan_adherence_share"], 0.5)
        self.assertIn("Plan adherence", metrics.markdown(s))


class DeliveryOutcomeTests(unittest.TestCase):
    def test_change_failure_rate_and_days_to_restore_come_from_spec_outcomes(self):
        import tempfile
        from pathlib import Path

        spec = '+++\naidd_version = "1.0.0"\nkind = "spec"\nid = "S-{n}"\n{extra}\n[outcome]\n{out}\n+++\n'
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "a.md").write_text(spec.format(n=1, extra="", out='released_at = "2026-09-01"\nobserve_result = "pass"'), encoding="utf-8")
            (root / "b.md").write_text(
                spec.format(n=2, extra="", out='released_at = "2026-09-02"\nrolled_back = true\nrestored_at = "2026-09-04"'), encoding="utf-8"
            )
            (root / "c.md").write_text(spec.format(n=3, extra="", out='observe_result = "fail"'), encoding="utf-8")  # never released: not counted
            (root / "notes.md").write_text("# not a Spec\n", encoding="utf-8")
            got = metrics.delivery_outcomes(root)
        self.assertEqual(got, {"released_specs": 2, "change_failure_rate": 0.5, "median_days_to_restore": 2})


if __name__ == "__main__":
    unittest.main()
