"""The approval digests: `aidd hash --line --summary` before Spec approval, and the Merge approval digest in the gate summary."""

import copy
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, git, run_cli

from aidd import digest, evals

SPEC = """+++
aidd_version = "1.0.0"
kind = "spec"
id = "SPEC-7"
title = "Refunds over the limit need a second approver"
owner_team = "payments"
type = "feat"
route = "normal"
confidence = "high"
open_questions = []
trace_id = "spec-7"
assisted_by = []
rollback = "Revert the PR; no data changes."
residual_risk = "A refund just under the limit still needs one approver."

[risk]
summary = "Refunds above 500 EUR wait for a second approver."
dimensions = ["financial"]
reversible = true

[[tasks]]
id = "SPEC-7-T1"
title = "Hold large refunds"
scope = ["src/refunds/"]

[tests]
files = ["tests/test_refunds.py"]

[[tests.commands]]
name = "refunds"
command = ["pytest", "-q", "tests/test_refunds.py"]
new_behavior = true
covers = ["A1", "A2"]
+++

## Intent

Finance: "a single agent approved a 4,000 EUR refund last week; that must take two people."

## Acceptance

{acceptance}
"""
TWO = "Scenario: A1 a refund above 500 EUR waits for a second approver\nScenario: A2 a refund of 500 EUR or less completes as today\nScenario: A3 the audit log names both approvers"


class SpecDigestTests(unittest.TestCase):
    def test_it_fits_a_phone_and_ends_with_the_approval_line(self):
        many = "\n".join(f"Scenario: A{i} behaviour number {i} of a long Spec" for i in range(1, 40))
        out = digest.spec_digest(SPEC.format(acceptance=many), "specs/SPEC-7.md", "/aidd approve-spec SPEC-7 abc def")
        lines = out.splitlines()
        self.assertLessEqual(len(lines), 25)
        self.assertLessEqual(max(len(x) for x in lines), 80)
        self.assertEqual(lines[-1], "/aidd approve-spec SPEC-7 abc def")
        self.assertIn("more in the Spec", out)
        for want in ("Intent: Finance", "A1 behaviour number 1", "Scope: src/refunds/", "[financial]", "Rollback: Revert", "Frozen: tests/test_refunds.py"):
            self.assertIn(want, out)

    def test_acceptance_ids_and_their_text(self):
        out = digest.spec_digest(SPEC.format(acceptance=TWO), "specs/SPEC-7.md", "h")
        self.assertIn("Acceptance (3):", out)
        self.assertIn("  A2 a refund of 500 EUR or less completes as today", out)
        self.assertIn("refunds (red first) covers A1/A2", out)

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_the_cli_prints_the_digest_and_the_line_the_gate_accepts(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            git(root, "init", "-q", "-b", "main")
            for k, v in (("user.email", "a@example.com"), ("user.name", "A"), ("commit.gpgsign", "false")):
                git(root, "config", k, v)
            (root / "specs").mkdir()
            (root / "specs/SPEC-7.md").write_text(SPEC.format(acceptance=TWO), encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests/test_refunds.py").write_text("assert False\n", encoding="utf-8")
            git(root, "add", ".")
            git(root, "commit", "-qm", "Spec")
            cwd = os.getcwd()
            os.chdir(root)
            try:
                code, plain = run_cli("hash", "specs/SPEC-7.md", "--line")
                code2, out = run_cli("hash", "specs/SPEC-7.md", "--line", "--summary")
            finally:
                os.chdir(cwd)
        self.assertEqual((code, code2), (0, 0))
        self.assertEqual(out.strip().splitlines()[-1], plain.strip())
        self.assertLessEqual(len(out.strip().splitlines()), 25)


class MergeDigestTests(unittest.TestCase):
    def setUp(self):
        self.ctx, _ = evals.load_example(ROOT / "examples" / "02-normal-feature")

    def test_the_worked_example(self):
        out = digest.merge_digest(copy.deepcopy(self.ctx))
        self.assertIn("#### Merge approval digest", out)
        self.assertIn("**Red on base:** yes", out)
        self.assertIn("**Residual risk:** A caller over the limit", out)
        self.assertIn("checkout-lead approved this head", out)
        self.assertNotIn("Spec-only", out)

    def test_acceptance_against_evidence_through_covers(self):
        ctx = copy.deepcopy(self.ctx)
        text = ctx["head_files"]["specs/SPEC-220.md"]
        text = text.replace("new_behavior = true\n+++", 'new_behavior = true\ncovers = ["A1"]\n+++')
        text = text.replace(
            "Given an authenticated caller", "Scenario: A1 request 61 gets HTTP 429\nScenario: A2 nothing proves this\nGiven an authenticated caller"
        )
        ctx["head_files"]["specs/SPEC-220.md"] = text
        out = digest.merge_digest(ctx)
        self.assertIn("| A1 request 61 gets HTTP 429 | `rate-limit` | passed | yes |", out)
        self.assertIn("| A2 nothing proves this | **nothing covers it** |", out)

    def test_review_findings_and_what_changed_since_the_last_approval(self):
        ctx = copy.deepcopy(self.ctx)
        ctx["comments"].append(
            {"user": "reviewer-bot", "body": "## Review\n\n- **Critical**: the limiter trusts X-Forwarded-For\n- Medium: naming\n- High: no metric on 429s\n"}
        )
        ctx["reviews"][0]["commit_sha"] = "c" * 40
        out = digest.merge_digest(ctx)
        self.assertIn("reported by reviewer-bot", out)
        self.assertIn("Critical: the limiter trusts X-Forwarded-For", out)
        self.assertIn("High: no metric on 429s", out)
        self.assertNotIn("naming", out)
        self.assertIn(f"was on {'c' * 12}", out)

    def test_a_spec_only_change_shows_its_tests_fail_on_base(self):
        ctx = copy.deepcopy(self.ctx)
        ctx["files"] = [f for f in ctx["files"] if not f["path"].startswith("src/")]
        for r in ctx["evidence"]["results"]:
            if r["name"] == "rate-limit" and r["red_green"] == "green":
                r.update(status="failed", exit=1)
        out = digest.merge_digest(ctx)
        self.assertIn("**Red on base:** yes", out)
        self.assertIn("Spec-only change", out)

    def test_red_on_base(self):
        self.assertEqual(digest.red_on_base(None), "not run")
        self.assertEqual(digest.red_on_base({"results": [{"red_green": "red", "status": "passed", "exit": 0}]}), "no")
        self.assertTrue(digest.red_on_base({"results": [{"red_green": "red", "status": "failed", "exit": 127}]}).startswith("inconclusive"))


if __name__ == "__main__":
    unittest.main()
