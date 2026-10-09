"""Attacks an agent (or a hurried human) might try. Every one must be blocked or held."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, decide, example, rules
from aidd import inputs, runner, util

FEATURE = "02-normal-feature"
MINOR = "01-minor-docs"


def add_file(ctx, path, a=5, d=0):
    ctx["files"].append({"path": path, "previous_path": None, "additions": a, "deletions": d})


class RedTeamTests(unittest.TestCase):
    def assertBlocked(self, d, rule, level="fail"):
        self.assertIn(rule, rules(d, level), f"{d.decision}: {[(f.rule, f.level, f.message) for f in d.findings]}")
        self.assertNotEqual(d.decision, "pass")

    def assertRaisedToMajor(self, d):
        """A protected-path edit in a normal Spec is raised to major, and the major gates then hold it."""
        self.assertEqual(d.record["route"], "major")
        self.assertIn("specialist_approval", rules(d, "pending"))
        self.assertNotEqual(d.decision, "pass")

    def test_baseline_feature_passes(self):
        self.assertEqual(decide(example(FEATURE)).decision, "pass")

    def test_forged_evidence_in_the_block_is_rejected(self):
        ctx = example(FEATURE)
        ctx["change"]["body"] = '```toml aidd\nspec = "specs/SPEC-220.md"\nchecks_results = "exit 0"\n```\n'
        self.assertBlocked(decide(ctx), "change_request")

    def test_missing_or_duplicate_block(self):
        ctx = example(FEATURE)
        ctx["change"]["body"] = "Trust me, tests pass."
        self.assertBlocked(decide(ctx), "change_request")
        ctx["change"]["body"] = '```toml aidd\nspec = "specs/SPEC-220.md"\n```\n```toml aidd\nspec = "specs/SPEC-220.md"\n```'
        self.assertBlocked(decide(ctx), "change_request")

    def test_agent_edits_the_aidd_config(self):
        ctx = example(FEATURE)
        add_file(ctx, ".aidd/config.toml")
        d = decide(ctx)
        self.assertRaisedToMajor(d)
        self.assertBlocked(d, "scope")

    def test_agent_edits_ci_or_agent_instructions(self):
        for path in (".github/workflows/aidd-gate.yml", "AGENTS.md", ".claude/settings.json", "CODEOWNERS"):
            ctx = example(FEATURE)
            add_file(ctx, path)
            self.assertRaisedToMajor(decide(ctx))

    def test_bootstrap_config_from_head_is_major(self):
        ctx = example(FEATURE)
        ctx["head_files"][".aidd/config.toml"] = ctx.pop("base_config")
        ctx["base_config"] = None
        add_file(ctx, ".aidd/config.toml")
        d = decide(ctx)
        self.assertIn("config", rules(d, "pending"))
        self.assertRaisedToMajor(d)

    def test_bootstrap_never_passes_even_when_clean(self):
        ctx = example(FEATURE)
        ctx["head_files"][".aidd/config.toml"] = ctx.pop("base_config").replace('profile = "team"', 'profile = "solo"')
        ctx["base_config"] = None
        self.assertBlocked(decide(ctx), "config", "pending")

    def test_tests_changed_after_spec_approval(self):
        ctx = example(FEATURE)
        ctx["head_tree"]["tests/checkout/test_rate_limit.py"] = "f" * 40
        self.assertBlocked(decide(ctx), "spec_approval", "pending")

    def test_acceptance_changed_after_spec_approval(self):
        ctx = example(FEATURE)
        ctx["head_files"]["specs/SPEC-220.md"] = ctx["head_files"]["specs/SPEC-220.md"].replace("61 requests", "600 requests")
        self.assertBlocked(decide(ctx), "spec_approval", "pending")

    def test_stale_review_on_older_commit(self):
        ctx = example(FEATURE)
        ctx["reviews"][0]["commit_sha"] = "0" * 40
        self.assertBlocked(decide(ctx), "merge_approval", "pending")

    def test_author_and_agent_cannot_approve(self):
        ctx = example(FEATURE)
        ctx["reviews"] = [
            {"user": "alice", "state": "approved", "commit_sha": ctx["head_sha"]},
            {"user": "claude[bot]", "state": "approved", "commit_sha": ctx["head_sha"]},
        ]
        self.assertBlocked(decide(ctx), "merge_approval", "pending")

    def test_author_cannot_approve_the_spec(self):
        ctx = example(FEATURE)
        ctx["comments"][0]["user"] = "alice"
        self.assertBlocked(decide(ctx), "spec_approval", "pending")

    def test_committer_counts_as_author(self):
        ctx = example(FEATURE)
        ctx["commits"][0]["committer"] = "checkout-lead"
        self.assertBlocked(decide(ctx), "merge_approval", "pending")

    def test_ineligible_approver(self):
        ctx = example(FEATURE)
        ctx["reviews"][0]["user"] = "random-dev"
        self.assertBlocked(decide(ctx), "merge_approval", "pending")

    def test_changes_requested_holds_the_gate(self):
        ctx = example(FEATURE)
        ctx["reviews"].append({"user": "platform-lead", "state": "changes_requested", "commit_sha": ctx["head_sha"], "submitted_at": "2026-09-23T09:40:00Z"})
        self.assertBlocked(decide(ctx), "merge_approval", "pending")

    def test_team_resolution(self):
        ctx = example(FEATURE)
        ctx["base_config"] = ctx["base_config"].replace('approvers = ["@checkout-lead", "@platform-lead", "@oncall-lead"]', 'approvers = ["@acme/checkout"]')
        ctx["team_members"] = {"@acme/checkout": ["checkout-lead"]}
        self.assertEqual(decide(ctx).decision, "pass")
        ctx["team_members"] = {}
        self.assertBlocked(decide(ctx), "merge_approval", "pending")

    def test_substituted_test_command(self):
        ctx = example(FEATURE)
        for r in ctx["evidence"]["results"]:
            if r["name"] == "rate-limit" and r["red_green"] == "green":
                r["command"] = ["true"]
        self.assertBlocked(decide(ctx), "tests")

    def test_missing_failing_or_timed_out_test(self):
        ctx = example(FEATURE)
        ctx["evidence"]["results"] = [r for r in ctx["evidence"]["results"] if r["name"] != "unit"]
        self.assertBlocked(decide(ctx), "tests")
        for status, code in (("failed", 1), ("timeout", None), ("not_started", None)):
            ctx = example(FEATURE)
            ctx["evidence"]["results"][0].update(status=status, exit=code)
            self.assertBlocked(decide(ctx), "tests")

    def test_no_evidence_or_stale_evidence(self):
        ctx = example(FEATURE)
        ctx["evidence"] = None
        self.assertBlocked(decide(ctx), "tests", "pending")
        ctx = example(FEATURE)
        ctx["evidence"]["head_sha"] = "e" * 40
        self.assertBlocked(decide(ctx), "tests", "pending")

    def test_red_run_must_fail_by_assertion(self):
        ctx = example(FEATURE)
        for r in ctx["evidence"]["results"]:
            if r["red_green"] == "red":
                r.update(status="failed", exit=127)
        self.assertBlocked(decide(ctx), "red_green")
        ctx = example(FEATURE)
        ctx["evidence"]["results"] = [r for r in ctx["evidence"]["results"] if r["red_green"] != "red"]
        self.assertBlocked(decide(ctx), "red_green")

    def test_scope_creep_and_budget(self):
        ctx = example(FEATURE)
        add_file(ctx, "src/payments/refund.ts")
        self.assertBlocked(decide(ctx), "scope")
        ctx = example(FEATURE)
        ctx["files"][2]["additions"] = 1000
        self.assertBlocked(decide(ctx), "budget")

    def test_policy(self):
        for result, rule, level in (("deny", "policy", "fail"), ("unreachable", "policy", "fail"), ("freeze", "policy", "fail")):
            ctx = example(FEATURE)
            ctx["policy"] = {"result": result}
            self.assertBlocked(decide(ctx), rule, level)

    def test_org_profile_needs_bound_policy_on_major(self):
        ctx = example("04-major-permission")
        ctx["base_config"] = ctx["base_config"].replace('profile = "team"', 'profile = "org"')
        self.assertBlocked(decide(ctx), "policy")

    def test_regulated_profile(self):
        ctx = example(FEATURE)
        ctx["base_config"] = ctx["base_config"].replace('profile = "team"', 'profile = "regulated"')
        ctx["base_config"] = ctx["base_config"].split("[[standard_changes]]")[0] + '[identities]\nbots = ["claude[bot]"]\n'
        ctx["commits"].append({"sha": "9" * 40, "author": "alice", "committer": "alice", "message": "Tidy", "merge": False})
        d = decide(ctx)
        for rule in ("policy", "observe", "provenance"):
            self.assertIn(rule, rules(d, "fail"))

    def test_provenance_must_match_trailers(self):
        ctx = example(MINOR)
        ctx["change"]["body"] = ctx["change"]["body"].replace('assisted_by = ["claude-code/claude-opus-5-5"]', "assisted_by = []")
        self.assertBlocked(decide(ctx), "provenance")

    def test_low_confidence_and_minor_limits(self):
        ctx = example(MINOR)
        ctx["change"]["body"] = ctx["change"]["body"].replace('confidence = "high"', 'confidence = "low"')
        self.assertBlocked(decide(ctx), "confidence")
        ctx = example(MINOR)
        ctx["files"][0]["additions"] = 80
        self.assertBlocked(decide(ctx), "route")

    def test_normal_route_needs_a_spec(self):
        ctx = example(MINOR)
        ctx["change"]["body"] = ctx["change"]["body"].replace('route = "minor"', 'route = "normal"')
        self.assertBlocked(decide(ctx), "spec")

    def test_standard_change_abuse(self):
        ctx = example("06-standard-dependency")
        ctx["change"]["author"] = "alice"
        self.assertBlocked(decide(ctx), "standard_change")
        ctx = example("06-standard-dependency")
        add_file(ctx, ".github/workflows/release.yml")
        self.assertBlocked(decide(ctx), "standard_change")
        ctx = example("06-standard-dependency")
        ctx["base_config"] = ctx["base_config"].replace('profile = "team"', 'profile = "regulated"')
        self.assertBlocked(decide(ctx), "standard_change")

    def test_major_specialist_approval(self):
        ctx = example("04-major-permission")
        ctx["reviews"] = [r for r in ctx["reviews"] if r["user"] != "sec-alice"]
        self.assertBlocked(decide(ctx), "specialist_approval", "pending")
        ctx = example("04-major-permission")
        ctx["base_config"] = ctx["base_config"].replace('[owners.specialists]\nsecurity = ["@sec-alice"]', "")
        self.assertBlocked(decide(ctx), "specialist_approval")

    def test_solo_cooloff(self):
        ctx = example("11-solo-major")
        ctx["comments"][1]["created_at"] = "2026-09-23T09:10:00Z"
        self.assertBlocked(decide(ctx), "merge_approval", "pending")
        ctx = example("11-solo-major")
        ctx["head_pushed_at"] = None
        self.assertBlocked(decide(ctx), "merge_approval", "pending")

    def test_emergency_review_due_within_sla(self):
        ctx = example("05-emergency-under-freeze")
        ctx["change"]["body"] = ctx["change"]["body"].replace("review_due = 2026-09-24", "review_due = 2026-10-30")
        self.assertBlocked(decide(ctx), "emergency")

    def test_draft_is_held(self):
        ctx = example(FEATURE)
        ctx["change"]["draft"] = True
        self.assertBlocked(decide(ctx), "draft", "pending")

    def test_loosening_gates_in_config_has_no_effect(self):
        ctx = example(FEATURE)
        ctx["base_config"] += "\n[gates]\nseparation_of_duties = false\napprovals = { normal = 0 }\n"
        ctx["reviews"] = []
        d = decide(ctx)
        self.assertBlocked(d, "merge_approval", "pending")
        self.assertIn("config", rules(d, "warn"))

    def test_every_example_is_a_trusted_context(self):
        for case in (ROOT / "examples").iterdir():
            if (case / "context.json").is_file():
                self.assertTrue(example(case.name)["trusted"])

    def test_runner_scrubs_secrets_from_child_processes(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "cmd.log"
            cmd = [sys.executable, "-c", "import os, json; print(json.dumps(dict(os.environ)))"]
            secret_env = {k: "secret_val" for k in util.SECRET_ENV}
            with mock.patch.dict(os.environ, secret_env):
                runner.execute(cmd, cwd=d, log=log, timeout=10)
            captured = json.loads(log.read_text(encoding="utf-8").strip())
            for k in util.SECRET_ENV:
                self.assertNotIn(k, captured)

    def test_runner_scrubs_every_credential_like_variable_unless_passed_by_name(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "cmd.log"
            cmd = [sys.executable, "-c", "import os, json; print(json.dumps(dict(os.environ)))"]
            creds = {"NPM_TOKEN": "t", "AWS_SECRET_ACCESS_KEY": "s", "DB_PASSWORD": "p", "STRIPE_API_KEY": "k", "HARMLESS": "h"}
            with mock.patch.dict(os.environ, creds):
                runner.execute(cmd, cwd=d, log=log, timeout=10)
                scrubbed = json.loads(log.read_text(encoding="utf-8").strip())
                runner.execute(cmd, cwd=d, log=log, timeout=10, pass_env=["NPM_TOKEN"])
                passed = json.loads(log.read_text(encoding="utf-8").strip())
            self.assertEqual({k for k in creds if k in scrubbed}, {"HARMLESS"})
            self.assertEqual({k for k in creds if k in passed}, {"HARMLESS", "NPM_TOKEN"})

    def test_extends_ssrf_non_public_addresses_refused(self):
        warns = []
        cfg = 'aidd_version = "1.0.0"\nprofile = "solo"\nextends = [{ url = "https://169.254.169.254/meta", sha256 = "' + ("0" * 64) + '" }]'
        out = inputs.collect_extends(cfg, read=lambda p: None, fetch=lambda u: "forbidden", warnings=warns)
        self.assertEqual(out, {})
        self.assertTrue(any("link-local" in w for w in warns))


if __name__ == "__main__":
    unittest.main()
