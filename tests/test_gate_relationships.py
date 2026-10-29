"""The gate checks the relationship, not one side of it.

Every case here is a way to satisfy a rule without proving anything: a frozen test rewritten after
approval, a duplicate evidence result, a command that cannot fail, an empty-diff approval proof, a
catch-all that probes miss, a timestamp sorted as a string, and an agent named as its own incident
commander under the one profile that waives separation of duties.
"""

import copy
import unittest

from helpers import SPEC_COMMIT, decide, example, rules

from aidd import config
from aidd.gate import rulebook
from aidd.gate import routing
from aidd.workitems import spec_file
from aidd.config import identities
from aidd.kernel import globs

FEATURE = "02-normal-feature"
EMERGENCY = "05-emergency-under-freeze"
TRIVIAL = "01-minor-docs"


class AuditGateTests(unittest.TestCase):
    def test_a_script_a_command_runs_is_frozen_however_it_is_named(self):
        """A script at the top, one with no extension that the command runs, and a `./` path are files the tests run
        through: Spec approval freezes them, and lint asks for them in tests.files. A program on PATH, a folder, an
        absolute path, and a version are not."""
        named = {
            ("bash", "test.sh"): ["test.sh"],
            ("python3", "run_tests.py"): ["run_tests.py"],
            ("scripts/run-tests",): ["scripts/run-tests"],
            ("./test",): ["test"],
            ("./scripts/test.sh", "--fast"): ["scripts/test.sh"],
            ("node", "--test", "check.mjs"): ["check.mjs"],
            ("pytest", "tests/test_x.py::test_one"): ["tests/test_x.py"],
            ("pytest", "-q", "tests/unit"): [],
            ("npm", "test"): [],
            ("uv", "run", "--python", "3.12", "pytest"): [],
            ("/usr/bin/env", "bash", "-c", "make test"): [],
            ("python3", "-m", "pytest"): [],
        }
        for command, want in named.items():
            with self.subTest(command=command):
                self.assertEqual(spec_file._path_literals(list(command)), want)
        spec = {
            "id": "SPEC-102",
            "title": "Scripts",
            "type": "feat",
            "route": "normal",
            "confidence": "high",
            "tasks": [{"id": "T1", "scope": ["src/"], "depends_on": []}],
            "tests": {"files": ["tests/"], "commands": [{"name": "unit", "command": ["bash", "test.sh"]}]},
        }
        errs = spec_file.lint_spec(spec, "## Context\nC\n## Acceptance\nA")
        self.assertTrue(any("'test.sh'" in e and "not covered by tests.files" in e for e in errs), errs)
        self.assertIn("test.sh", spec_file.frozen_paths(spec))

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
        errs = spec_file.lint_spec(spec, body)
        self.assertTrue(
            any("audit-gate" in e and "tests/checkout/test_rate_limit.py" in e and "not covered by tests.files" in e for e in errs),
            errs,
        )

        frozen = spec_file.frozen_paths(spec)
        self.assertIn("tests/checkout/test_rate_limit.py", frozen)

        tree1 = {"tests/checkout/test_rate_limit.py": "blob_aaa111"}
        tree2 = {"tests/checkout/test_rate_limit.py": "blob_bbb222"}
        spec_text_c1 = (
            '---\naidd_version: "1.0.0"\nkind: spec\nid: SPEC-101\ntitle: C1\nowner_team: dev\n'
            "type: feat\nroute: normal\nconfidence: high\n\n"
            "tasks:\n  - id: T1\n    title: T1\n    scope: [src/]\n\n"
            "tests:\n  files: [tests/smoke/]\n\n"
            "  commands:\n    - name: audit-gate\n      command: [pytest, tests/checkout/test_rate_limit.py]\n---\n"
            "## Context\nC\n## Acceptance\nA\n"
        )
        h_cmd1 = spec_file.spec_hash(spec_text_c1, tree1)
        h_cmd2 = spec_file.spec_hash(spec_text_c1, tree2)
        self.assertNotEqual(h_cmd1, h_cmd2)

    def test_duplicate_evidence_results_folding(self):
        """Duplicate evidence results with failed and passed fail closed regardless of array order."""
        for order in (
            [
                {"name": "unit", "red_green": "green", "command": ["make", "test"], "status": "failed", "exit": 1},
                {"name": "unit", "red_green": "green", "command": ["make", "test"], "status": "passed", "exit": 0},
            ],
            [
                {"name": "unit", "red_green": "green", "command": ["make", "test"], "status": "passed", "exit": 0},
                {"name": "unit", "red_green": "green", "command": ["make", "test"], "status": "failed", "exit": 1},
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
            bad_spec = spec_text.replace("command: [pytest, -q, tests/checkout/test_rate_limit.py]", f"command: {list(bad_cmd)}")
            ctx["head_files"]["specs/SPEC-220.md"] = bad_spec
            ctx["evidence"]["results"] = [
                {"name": "unit", "red_green": "green", "command": ["make", "test"], "status": "passed", "exit": 0},
                {"name": "rate-limit", "red_green": "green", "command": bad_cmd, "status": "passed", "exit": 0},
            ]
            d = decide(ctx)
            self.assertEqual(d.decision, "fail")
            self.assertIn("tests", rules(d, "fail"))
            noop = [f.level for f in d.findings if f.rule == "tests" and "proves nothing" in f.message]
            self.assertEqual(noop, ["fail"])  # one finding, not a fail and a duplicate warn

        from aidd.gate.rules.evidence import is_no_op_command

        self.assertFalse(is_no_op_command(["pytest", "-q", "tests/x.py"]))
        self.assertFalse(is_no_op_command(["sh", "-c", "pytest && true"]))

    def test_approval_commit_proof_requires_non_empty_diff(self):
        """/aidd approve-spec naming a commit with empty diff or naming base_sha does not prove Spec approval."""
        ctx = example(FEATURE)
        ctx["base_config"] += "\ngates:\n  spec_approval_proof: require\n"
        base_sha, empty = ctx["base_sha"], "e" * 40
        h = ctx["approval_commits"][SPEC_COMMIT]["spec_hash"]
        ctx["approval_commits"] = {
            empty: {"ancestor": True, "paths": [], "spec_hash": h},
            base_sha: {"ancestor": True, "paths": [], "spec_hash": h},
        }
        for c in ctx["comments"]:
            if "/aidd approve-spec" in c["body"]:
                c["body"] = c["body"].replace(SPEC_COMMIT, empty)
        d = decide(ctx)
        self.assertFalse(d.record.get("spec_approval_before_implementation"))
        self.assertIn("spec_approval", rules(d, "pending"))

        # Case 2: approve naming base_sha directly
        for c in ctx["comments"]:
            if "/aidd approve-spec" in c["body"]:
                c["body"] = c["body"].replace(empty, base_sha)
        d2 = decide(ctx)
        self.assertFalse(d2.record.get("spec_approval_before_implementation"))
        self.assertTrue(any("approval names the base commit" in f.message for f in d2.findings if f.rule == "spec_approval"))

    def test_catch_all_structural_detection(self):
        """Catch-all detection matches patterns spanning hierarchy without a fixed root."""
        for p in ("**/*.*", "**/*.py", "**/*.ts", "**/*", "**"):
            self.assertTrue(globs.is_catch_all(p), f"Expected True for {p}")
        for p in ("src/**", "tests/**/*.py", "docs/", "*", "*.md"):
            self.assertFalse(globs.is_catch_all(p), f"Expected False for {p}")

        cfg_text = 'aidd_version: "1.0.0"\nprofile: team\nchanged_lines_exclude_paths: ["**/*.*"]\n'
        c = config.load_text(cfg_text)
        self.assertTrue(any("changed_lines_exclude_paths" in w and "ignored" in w for w in c.warnings))
        self.assertEqual(c.get("changed_lines_exclude_paths"), [])

    def test_unguarded_grants_dropped_and_warned(self):
        """Grants in rule_exclusions, standard_changes, owners.paths, and risk_rules are guarded."""
        cfg_text = """
aidd_version: "1.0.0"
profile: solo
rule_exclusions: {"baseline:migrations": ["**"]}
standard_changes:
  - name: deps
    paths: ["**"]
    authors: ["@dependabot"]
owners:
  approvers: ["@lead"]
  paths: [{paths: ["**"], approvers: ["@sec"]}]
risk_rules:
  - name: custom
    paths: ["src/**"]
    exclude: ["**"]
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
            ctx["base_config"] = ctx["base_config"].replace("profile: org", "profile: solo")
            ctx["change"]["body"] = ctx["change"]["body"].replace('commander: "@oncall-lead"', f'commander: "{agent}"')
            d = decide(ctx)
            self.assertEqual(d.decision, "fail")
            self.assertIn("emergency", rules(d, "fail"))
            self.assertTrue(any("is an agent or bot account" in f.message for f in d.findings if f.rule == "emergency"))

        ctx = example(EMERGENCY)
        ctx["base_config"] = ctx["base_config"].replace("profile: org", "profile: solo")
        ctx["change"]["body"] = ctx["change"]["body"].replace('commander: "@oncall-lead"', 'commander: "@claude-martin"')
        d = decide(ctx)
        # A person whose name holds an agent's word is no agent; under solo they must still be an Approver.
        self.assertNotIn("fail emergency.commander_is_agent", d.codes())
        self.assertIn("fail emergency.commander_not_approver", d.codes())

    def test_overlap_supports_question_mark(self):
        """Globs.overlap handles '?' wildcard."""
        self.assertTrue(globs.overlap("?ests/x.py", "tests/x.py"))

    def test_change_block_indented_and_fenced(self):
        """Change Request blocks indented by 1-3 spaces are recognized; blocks inside outer fences are ignored."""
        indented = "   ```yaml aidd\nroute: minor\ntype: chore\nassisted_by: []\n```\n"
        data, errs = spec_file.parse_change_block(indented)
        self.assertEqual(errs, [])
        self.assertIsNotNone(data)
        self.assertEqual(data["route"], "minor")

        nested = "````markdown\n```yaml aidd\nroute: minor\ntype: chore\nassisted_by: []\n```\n````\n"
        data_nested, _ = spec_file.parse_change_block(nested)
        self.assertIsNone(data_nested)

    def test_provenance_trailer_block_anchoring(self):
        """Assisted-by in code block does not count as trailer, and trailer values must be in assisted_by."""
        body_with_fenced_trailer = "Commit title\n\n```diff\n+ Assisted-by: none\n```\n\nExplanation text."
        trailers = identities.extract_trailers(body_with_fenced_trailer)
        self.assertEqual(trailers, [])

        ctx = example(FEATURE)
        ctx["commits"][0]["message"] += "\n\nAssisted-by: custom-harness/model-x"
        ctx["head_files"]["specs/SPEC-220.md"] = ctx["head_files"]["specs/SPEC-220.md"].replace(
            "assisted_by: [claude-code/claude-opus-5-5]", "assisted_by: [other/model]"
        )
        d = decide(ctx)
        self.assertIn("provenance", rules(d, "fail"))
        self.assertTrue(any("not declared in assisted_by" in f.message for f in d.findings if f.rule == "provenance"))

    def test_rulebook_explain_policy_rules(self):
        """Aidd gate --explain policy:ticket prints policy rule row and exits 0."""
        text = rulebook.explain_rule("policy:ticket")
        self.assertIn("policy:ticket", text)
        self.assertIn("holds when:", text)
        self.assertIn("to satisfy:", text)

        with self.assertRaises(LookupError):
            rulebook.explain_rule("nonexistent_rule")

    def test_explain_takes_a_finding_code_and_leads_with_it(self):
        """`aidd gate --explain scope.outside`: the code's meaning and fix first, then its rule's row."""
        text = rulebook.explain_rule("scope.outside")
        self.assertTrue(text.startswith(f"scope.outside: {rulebook.BY_NAME['scope'].codes['scope.outside']}\n  to fix: "))
        self.assertLess(text.index("to fix:"), text.index("scope (fail or warn)"))
        self.assertIn("holds when:", text)
        # spec.missing, which once exited 2 as an unknown rule.
        self.assertIn(
            "spec.missing: normal or major, as the block declares or the gate computes with no block, and no Spec", rulebook.explain_rule("spec.missing")
        )
        with self.assertRaisesRegex(LookupError, r"no finding code 'scope\.nowhere'; `aidd gate --explain scope` lists its codes"):
            rulebook.explain_rule("scope.nowhere")
        with self.assertRaisesRegex(LookupError, "no finding code 'nope.x'; the rules are context"):
            rulebook.explain_rule("nope.x")

    def test_a_code_with_its_own_fix_shows_it_and_others_take_the_rules(self):
        rule = rulebook.Rule("demo", "fail", "holds", "the rule's fix", codes={"demo.a": "a", "demo.b": "b"}, fixes={"demo.b": "b's own fix"})
        self.assertEqual(rule.fix_for("demo.a"), "the rule's fix")
        self.assertEqual(rule.fix_for("demo.b"), "b's own fix")
        for r in rulebook.RULES:
            self.assertLessEqual(set(r.fixes), set(r.codes), f"{r.name}: a fix for a code the row does not list")

    def test_the_report_shows_each_finding_by_its_code(self):
        from aidd.gate import decision_report

        d = decide(example("08-scope-creep"))
        self.assertIn("fail scope.outside", d.codes())
        text = decision_report.decision_text(d)
        outside = next(f for f in d.findings if f.code == "scope.outside")
        self.assertIn(f"  [FAIL] scope.outside: {outside.message}", text)
        markdown = decision_report.decision_markdown(d)
        self.assertIn("| | Code | Finding | Fix |", markdown)
        self.assertIn("| :x: | [`scope.outside`](https://github.com/thaithienvanid/aidd/blob/main/docs/ERRORS.md#scope-outside) | ", markdown)
        # The adapter passes the commit aidd runs from, so the row matches the code.
        pinned = decision_report.decision_markdown(d, "0123456789abcdef0123456789abcdef01234567")
        self.assertIn("(https://github.com/thaithienvanid/aidd/blob/0123456789abcdef0123456789abcdef01234567/docs/ERRORS.md#scope-outside)", pinned)

    def test_a_crash_and_a_bad_context_name_the_bug_report(self):
        d = decide({"not": "a context"})
        self.assertTrue(d.findings)
        self.assertTrue(all(rulebook.BUG_REPORT_URL in f.fix for f in d.findings))
        self.assertIn(rulebook.BUG_REPORT_URL, rulebook.BY_NAME["internal"].fix)

    def test_case_folding_and_empty_approvers(self):
        """Standard_match matches grant paths exactly (folding case would widen a grant that
        merges without a human), and an empty spec approvers list narrows to an empty pool."""
        entry = {"name": "ci", "paths": ["CI/config.yml"], "authors": ["@bot"]}
        problems = routing.standard_match(entry, paths=["ci/config.yml"], identities={"bot"}, changed_lines=5)
        self.assertTrue(problems)
        self.assertEqual(routing.standard_match(entry, paths=["CI/config.yml"], identities={"bot"}, changed_lines=5), [])

        ctx = example(FEATURE)
        spec_text = ctx["head_files"]["specs/SPEC-220.md"]
        head, sep, tail = spec_text.partition("\nrisk:")
        spec_with_empty_approvers = head + "\napprovers: []\n" + sep + tail
        ctx["head_files"]["specs/SPEC-220.md"] = spec_with_empty_approvers
        h = spec_file.spec_hash(spec_with_empty_approvers, ctx["head_tree"])
        ctx["comments"] = [{"user": "checkout-lead", "body": f"/aidd approve-spec SPEC-220 {h}", "created_at": "2026-09-23T08:00:00Z"}]
        d = decide(ctx)
        self.assertIn("spec_approval", rules(d, "pending"))
        self.assertEqual(d.record.get("spec_approved_by"), [])


if __name__ == "__main__":
    unittest.main()
