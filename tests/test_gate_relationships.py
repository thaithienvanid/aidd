"""The gate checks the relationship, not one side of it.

Every case here is a way to satisfy a rule without proving anything: a frozen test rewritten after
approval, a duplicate evidence result, a command that cannot fail, an empty-diff approval proof, a
catch-all that probes miss, a timestamp sorted as a string, and an agent named as its own incident
commander under the one profile that waives separation of duties.
"""

import copy
import unittest

from helpers import decide, example, rules

from aidd import config, globs, model, rulebook, rules as aidd_rules, util

FEATURE = "02-normal-feature"
EMERGENCY = "05-emergency-under-freeze"
TRIVIAL = "01-minor-docs"


class AuditGateTests(unittest.TestCase):
    def test_tests_commands_not_covered_by_tests_files(self):
        """Lint_spec flags command test paths not in tests.files, and spec_hash freezes them."""
        spec = {
            "id": "SPEC-101",
            "title": "Test C1",
            "type": "feat",
            "route": "normal",
            "confidence": "high",
            "tasks": [{"id": "T1", "scope": ["src/"], "depends_on": []}],
            "tests": {
                "files": ["tests/smoke/"],
                "commands": [{"name": "audit-gate", "command": ["pytest", "-q", "tests/checkout/test_rate_limit.py"]}],
            },
        }
        body = "## Context\nTest\n## Acceptance\nTest"
        errs = model.lint_spec(spec, body)
        self.assertTrue(
            any("audit-gate" in e and "tests/checkout/test_rate_limit.py" in e and "not covered by tests.files" in e for e in errs),
            errs,
        )

        frozen = model.frozen_paths(spec)
        self.assertIn("tests/checkout/test_rate_limit.py", frozen)

        tree1 = {"tests/checkout/test_rate_limit.py": "blob_aaa111"}
        tree2 = {"tests/checkout/test_rate_limit.py": "blob_bbb222"}
        spec_text_c1 = (
            '+++\naidd_version = "1.0.0"\nkind = "spec"\nid = "SPEC-101"\ntitle = "C1"\nowner_team = "dev"\n'
            'type = "feat"\nroute = "normal"\nconfidence = "high"\n\n'
            '[[tasks]]\nid = "T1"\ntitle = "T1"\nscope = ["src/"]\n\n'
            '[tests]\nfiles = ["tests/smoke/"]\n\n'
            '[[tests.commands]]\nname = "audit-gate"\ncommand = ["pytest", "tests/checkout/test_rate_limit.py"]\n+++\n'
            "## Context\nC\n## Acceptance\nA\n"
        )
        h_cmd1 = model.spec_hash(spec_text_c1, tree1)
        h_cmd2 = model.spec_hash(spec_text_c1, tree2)
        self.assertNotEqual(h_cmd1, h_cmd2)

    def test_duplicate_evidence_results_folding(self):
        """Duplicate evidence results with failed and passed fail closed regardless of array order."""
        for order in (
            [
                {"name": "unit", "phase": "green", "command": ["make", "test"], "status": "failed", "exit": 1},
                {"name": "unit", "phase": "green", "command": ["make", "test"], "status": "passed", "exit": 0},
            ],
            [
                {"name": "unit", "phase": "green", "command": ["make", "test"], "status": "passed", "exit": 0},
                {"name": "unit", "phase": "green", "command": ["make", "test"], "status": "failed", "exit": 1},
            ],
        ):
            ctx = example(FEATURE)
            ctx["evidence"]["results"] = order
            d = decide(ctx)
            self.assertEqual(d.decision, "fail")
            self.assertIn("tests", rules(d, "fail"))
            findings = [f.message for f in d.findings if f.rule == "tests"]
            self.assertTrue(any("duplicate test result 'unit' in phase 'green'" in msg for msg in findings))
            self.assertTrue(any(t["name"] == "unit" and t["status"] == "failed" for t in d.record.get("tests", [])))

    def test_no_op_commands_rejected(self):
        """Command that cannot fail is rejected on any route and type."""
        for bad_cmd in (["python3", "-c", "pass"], ["/bin/sh", "-c", "exit 0"], ["env", "true"], ["make", "noop"]):
            ctx = example(FEATURE)
            spec_text = ctx["head_files"]["specs/SPEC-220.md"]
            bad_spec = spec_text.replace('command = ["pytest", "-q", "tests/checkout/test_rate_limit.py"]', f"command = {list(bad_cmd)}")
            ctx["head_files"]["specs/SPEC-220.md"] = bad_spec
            ctx["evidence"]["results"] = [
                {"name": "unit", "phase": "green", "command": ["make", "test"], "status": "passed", "exit": 0},
                {"name": "rate-limit", "phase": "green", "command": bad_cmd, "status": "passed", "exit": 0},
            ]
            d = decide(ctx)
            self.assertEqual(d.decision, "fail")
            self.assertIn("tests", rules(d, "fail"))
            noop = [f.level for f in d.findings if f.rule == "tests" and "proves nothing" in f.message]
            self.assertEqual(noop, ["fail"])  # one finding, not a fail and a duplicate warn

        from aidd.gates import is_no_op_command

        self.assertFalse(is_no_op_command(["pytest", "-q", "tests/x.py"]))
        self.assertFalse(is_no_op_command(["sh", "-c", "pytest && true"]))

    def test_approval_commit_proof_requires_non_empty_diff(self):
        """/aidd approve-spec naming a commit with empty diff or naming base_sha does not prove Spec approval."""
        ctx = example(FEATURE)
        ctx["base_config"] += '\n[gates]\nspec_approval_proof = "require"\n'
        base_sha = ctx["base_sha"]
        ctx["approval_commits"] = {
            "empty111": {"ancestor": True, "paths": []},
            base_sha: {"ancestor": True, "paths": []},
        }
        for c in ctx["comments"]:
            if "/aidd approve-spec" in c["body"]:
                c["body"] = c["body"] + " empty111"
        d = decide(ctx)
        self.assertFalse(d.record.get("spec_approval_before_implementation"))
        self.assertIn("spec_approval", rules(d, "pending"))

        # Case 2: approve naming base_sha directly
        for c in ctx["comments"]:
            if "/aidd approve-spec" in c["body"]:
                c["body"] = c["body"].replace("empty111", base_sha)
        d2 = decide(ctx)
        self.assertFalse(d2.record.get("spec_approval_before_implementation"))
        self.assertTrue(any("approval names the base commit" in f.message for f in d2.findings if f.rule == "spec_approval"))

    def test_catch_all_structural_detection(self):
        """Catch-all detection matches patterns spanning hierarchy without a fixed root."""
        for p in ("**/*.*", "**/*.py", "**/*.ts", "**/*", "**"):
            self.assertTrue(globs.is_catch_all(p), f"Expected True for {p}")
        for p in ("src/**", "tests/**/*.py", "docs/", "*", "*.md"):
            self.assertFalse(globs.is_catch_all(p), f"Expected False for {p}")

        cfg_text = 'aidd_version = "1.0.0"\nprofile = "team"\nbudget_exclude_paths = ["**/*.*"]\n'
        c = config.load_text(cfg_text)
        self.assertTrue(any("budget_exclude_paths" in w and "ignored" in w for w in c.warnings))
        self.assertEqual(c.get("budget_exclude_paths"), [])

    def test_unguarded_grants_dropped_and_warned(self):
        """Grants in rule_exclusions, standard_changes, owners.paths, and risk_rules are guarded."""
        cfg_text = """
aidd_version = "1.0.0"
profile = "solo"
rule_exclusions = {"baseline:migrations" = ["**"]}
[[standard_changes]]
name = "deps"
paths = ["**"]
authors = ["@dependabot"]
[owners]
approvers = ["@lead"]
paths = [{ paths = ["**"], approvers = ["@sec"] }]
[[risk_rules]]
name = "custom"
paths = ["src/**"]
exclude = ["**"]
"""
        c = config.load_text(cfg_text)
        warn_text = "\n".join(c.warnings)
        self.assertIn("rule_exclusions 'baseline:migrations'", warn_text)
        self.assertIn("standard_changes 'deps' paths", warn_text)
        self.assertIn("owners.paths", warn_text)
        self.assertIn("risk_rules exclude", warn_text)
        self.assertEqual(c.get("rule_exclusions")["baseline:migrations"], [])
        self.assertEqual(c.get("standard_changes")[0]["paths"], [])
        self.assertEqual(c.get("owners")["paths"][0]["paths"], [])
        self.assertEqual(c.get("risk_rules")[0]["exclude"], [])

    def test_review_ordering_by_instant(self):
        """Reviews are sorted by parsed instant so differing timezone offsets do not invert state."""
        ctx0 = example(FEATURE)
        head = ctx0["head_sha"]
        rev_approved = {"user": "checkout-lead", "state": "approved", "submitted_at": "2026-09-23T12:00:00+05:00", "commit_sha": head}
        rev_changes = {"user": "checkout-lead", "state": "changes_requested", "submitted_at": "2026-09-23T09:00:00Z", "commit_sha": head}

        for revs in ([rev_approved, rev_changes], [rev_changes, rev_approved]):
            ctx = example(FEATURE)
            ctx["reviews"] = copy.deepcopy(revs)
            d = decide(ctx)
            # Latest state for checkout-lead must be changes_requested (09:00Z is after 07:00Z)
            self.assertIn("merge_approval", rules(d, "pending"))
            self.assertEqual(d.record.get("approved_by"), [])

        # Review with no submitted_at gets _EPOCH and does not override dated review
        rev_nodate = {"user": "checkout-lead", "state": "changes_requested", "commit_sha": head}
        ctx = example(FEATURE)
        ctx["reviews"] = [rev_nodate, rev_approved]
        d = decide(ctx)
        self.assertEqual(d.record.get("approved_by"), ["checkout-lead"])

    def test_emergency_commander_agent_bot_rejected(self):
        """Emergency incident commander cannot be an AI agent or bot even under solo."""
        for agent in ("@claude", "@copilot", "@codex", "@cursor", "@gemini", "@deepseek", "@grok", "@opencode", "@web-flow", "@github-actions", "@ghost"):
            ctx = example(EMERGENCY)
            ctx["base_config"] = ctx["base_config"].replace('profile = "org"', 'profile = "solo"')
            ctx["change"]["body"] = ctx["change"]["body"].replace('commander = "@oncall-lead"', f'commander = "{agent}"')
            d = decide(ctx)
            self.assertEqual(d.decision, "fail")
            self.assertIn("emergency", rules(d, "fail"))
            self.assertTrue(any("is an agent or bot account" in f.message for f in d.findings if f.rule == "emergency"))

        ctx = example(EMERGENCY)
        ctx["base_config"] = ctx["base_config"].replace('profile = "org"', 'profile = "solo"')
        ctx["change"]["body"] = ctx["change"]["body"].replace('commander = "@oncall-lead"', 'commander = "@claude-martin"')
        d = decide(ctx)
        self.assertNotIn("emergency", rules(d, "fail"))

    def test_overlap_supports_question_mark(self):
        """Globs.overlap handles '?' wildcard."""
        self.assertTrue(globs.overlap("?ests/x.py", "tests/x.py"))

    def test_change_block_indented_and_fenced(self):
        """Change Request blocks indented by 1-3 spaces are recognized; blocks inside outer fences are ignored."""
        indented = '   ```toml aidd\nroute = "minor"\ntype = "chore"\nassisted_by = []\n```\n'
        data, errs = model.parse_change_block(indented)
        self.assertEqual(errs, [])
        self.assertIsNotNone(data)
        self.assertEqual(data["route"], "minor")

        nested = '````markdown\n```toml aidd\nroute = "minor"\ntype = "chore"\nassisted_by = []\n```\n````\n'
        data_nested, _ = model.parse_change_block(nested)
        self.assertIsNone(data_nested)

    def test_provenance_trailer_block_anchoring(self):
        """Assisted-by in code block does not count as trailer, and trailer values must be in assisted_by."""
        body_with_fenced_trailer = "Commit title\n\n```diff\n+ Assisted-by: none\n```\n\nExplanation text."
        trailers = util.extract_trailers(body_with_fenced_trailer)
        self.assertEqual(trailers, [])

        ctx = example(FEATURE)
        ctx["commits"][0]["message"] += "\n\nAssisted-by: custom-harness/model-x"
        ctx["head_files"]["specs/SPEC-220.md"] = ctx["head_files"]["specs/SPEC-220.md"].replace(
            'assisted_by = ["claude-code/claude-opus-5-5"]', 'assisted_by = ["other/model"]'
        )
        d = decide(ctx)
        self.assertIn("provenance", rules(d, "fail"))
        self.assertTrue(any("not declared in assisted_by" in f.message for f in d.findings if f.rule == "provenance"))

    def test_rulebook_explain_policy_rules(self):
        """Aidd gate --explain policy:ticket prints policy rule row and exits 0."""
        text = rulebook.explain("policy:ticket")
        self.assertIn("policy:ticket", text)
        self.assertIn("holds when:", text)
        self.assertIn("to satisfy:", text)

        with self.assertRaises(LookupError):
            rulebook.explain("nonexistent_rule")

    def test_case_folding_and_empty_approvers(self):
        """Standard_match matches grant paths exactly (folding case would widen a grant that
        merges without a human), and an empty spec approvers list narrows to an empty pool."""
        entry = {"name": "ci", "paths": ["CI/config.yml"], "authors": ["@bot"]}
        problems = aidd_rules.standard_match(entry, paths=["ci/config.yml"], identities={"bot"}, changed_lines=5)
        self.assertTrue(problems)
        self.assertEqual(aidd_rules.standard_match(entry, paths=["CI/config.yml"], identities={"bot"}, changed_lines=5), [])

        ctx = example(FEATURE)
        spec_text = ctx["head_files"]["specs/SPEC-220.md"]
        head, sep, tail = spec_text.partition("[risk]")
        spec_with_empty_approvers = head + "approvers = []\n\n" + sep + tail
        ctx["head_files"]["specs/SPEC-220.md"] = spec_with_empty_approvers
        h = model.spec_hash(spec_with_empty_approvers, ctx["head_tree"])
        ctx["comments"] = [{"user": "checkout-lead", "body": f"/aidd approve-spec SPEC-220 {h}", "created_at": "2026-09-23T08:00:00Z"}]
        d = decide(ctx)
        self.assertIn("spec_approval", rules(d, "pending"))
        self.assertEqual(d.record.get("spec_approved_by"), [])


if __name__ == "__main__":
    unittest.main()
