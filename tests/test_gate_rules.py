import copy
import unittest
from unittest import mock

from helpers import FakeTransport, ROOT, decide, example, package_source, rules, source_of

from aidd import config
from aidd.platforms import github
from aidd.gate import rulebook
from aidd.gate import rules as gates
from aidd.gate import routing
from aidd.workitems import spec_file
from aidd.kernel import documents, globs

TRIVIAL = "01-minor-docs"
FEATURE = "02-normal-feature"
API = "https://api.github.test"


def add_file(ctx, path, lines=3):
    ctx["files"].append({"path": path, "previous_path": None, "additions": lines, "deletions": 0, "binary": False})


def inline(ctx, old, new):
    assert old in ctx["change"]["body"], old
    ctx["change"]["body"] = ctx["change"]["body"].replace(old, new)


def without_suite(ctx):
    text = ctx["base_config"]
    head, _, rest = text.partition("\ntests:\n")
    lines = rest.splitlines(keepends=True)
    while lines and (not lines[0].strip() or lines[0][0] in " -"):
        lines.pop(0)
    ctx["base_config"] = head + "\n" + "".join(lines)


class ScopeCatchAllTests(unittest.TestCase):
    """A catch-all glob must never grant scope."""

    def test_inline_checks_paths_catch_all(self):
        ctx = example(TRIVIAL)
        inline(ctx, "reversible: true\n```", 'reversible: true\ntests:\n  files: ["**"]\n  commands:\n    - name: x\n      command: [make, docs]\n```')
        add_file(ctx, "src/payments/refund.ts")
        self.assertIn("scope", rules(decide(ctx), "fail"))

    def test_inline_scope_catch_all(self):
        ctx = example(TRIVIAL)
        inline(ctx, "scope: [docs/guide.md]", 'scope: ["**"]')
        self.assertIn("scope", rules(decide(ctx), "fail"))

    def test_spec_checks_paths_catch_all(self):
        spec, body = documents.split_front_matter(example(FEATURE)["head_files"]["specs/SPEC-220.md"])
        spec["tests"]["files"] = ["**/*"]
        self.assertTrue(any("matches every path" in e for e in spec_file.lint_spec(spec, body)))

    def test_catch_all_detection(self):
        for p in ("**", "**/*", "**/"):
            self.assertTrue(globs.is_catch_all(p), p)
        for p in ("*", "src/**", "docs/", "*.md"):
            self.assertFalse(globs.is_catch_all(p), p)


class TestApplicabilityTests(unittest.TestCase):
    def test_when_changed_suite_that_misses_is_not_a_failure(self):
        """A suite scoped by when_changed does not fail a change it does not cover."""
        ctx = example(TRIVIAL)
        ctx["base_config"] = ctx["base_config"].replace("command: [make, test]", 'command: [make, test]\n    when_changed: ["services/api/**"]')
        d = decide(ctx)
        self.assertNotIn("tests", rules(d, "fail"))
        self.assertIn("tests", rules(d, "warn"))

    def test_minor_cannot_replace_a_missing_suite(self):
        """With no repository suite, an inline `true` does not make a minor change proven."""
        ctx = example(TRIVIAL)
        without_suite(ctx)
        self.assertNotIn("tests", documents.parse_yaml(ctx["base_config"], "config"))
        inline(ctx, "reversible: true\n```", 'reversible: true\ntests:\n  files: [tests/smoke.sh]\n  commands:\n    - name: noop\n      command: ["true"]\n```')
        d = decide(ctx)
        self.assertIn("tests", rules(d, "fail"))
        self.assertTrue(any("proves nothing" in f.message for f in d.findings if f.level == "fail"))


class ApprovalParsingTests(unittest.TestCase):
    """Approval lines in code, quotes, or comments never count."""

    def spec_comment(self, ctx):
        return next(c for c in ctx["comments"] if "approve-spec" in c["body"])

    def test_code_and_indentation_do_not_count(self):
        for wrap in ("Do not post yet:\n\n    {}", "```\n{}", "<!-- {} -->", "  {}"):
            ctx = example(FEATURE)
            c = self.spec_comment(ctx)
            c["body"] = wrap.format(c["body"])
            self.assertIn("spec_approval", rules(decide(ctx), "pending"), wrap)

    def test_plain_line_still_counts(self):
        ctx = example(FEATURE)
        c = self.spec_comment(ctx)
        c["body"] = f"Looks good.\n\n{c['body']}\n"
        self.assertEqual(decide(ctx).decision, "pass")


class IdentityTests(unittest.TestCase):
    def test_ignore_cannot_exempt_a_person(self):
        """A co-committing human stays an author even when listed in identities.system_accounts."""
        ctx = example(FEATURE)
        ctx["commits"].append(dict(ctx["commits"][0], sha="2" * 40, author="checkout-lead", committer="checkout-lead"))
        ctx["base_config"] = ctx["base_config"].replace("system_accounts: [web-flow]", "system_accounts: [web-flow, checkout-lead]")
        d = decide(ctx)
        self.assertNotEqual(d.decision, "pass")
        self.assertTrue(any("ignore" in f.message for f in d.findings if f.level == "warn"))

    def test_a_lookalike_of_a_system_account_stays_an_author(self):
        """Commit author text is the committer's to write, so a fullwidth or zero-width lookalike of a system account
        never folds into it: the commit's author still counts as a person."""
        for lookalike in ("\uff57eb-flow", "web-flow\u200b", "\uff47ithub-actions[bot]"):
            with self.subTest(lookalike=lookalike.encode("unicode_escape").decode()):
                ctx = example(FEATURE)
                ctx["base_config"] = ctx["base_config"].replace("system_accounts: [web-flow]", 'system_accounts: [web-flow, "github-actions[bot]"]')
                ctx["commits"].append(dict(ctx["commits"][0], sha="2" * 40, author=lookalike, committer=lookalike))
                self.assertIn(config.normalize_identity(lookalike), decide(ctx).record["authors"])

    def test_a_lookalike_bot_commit_is_no_standard_change(self):
        from aidd.gate.rules import declared

        cfg = config.load_text(
            'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@x"]\nidentities:\n'
            '  system_accounts: [web-flow, "github-actions[bot]"]\n'
            'standard_changes:\n  - name: deps\n    paths: [package.json]\n    authors: ["dependabot[bot]"]\n'
        )

        def ctx(committer):
            return {"commits": [{"author": "dependabot[bot]", "committer": committer}], "change": {"author": "dependabot[bot]"}}

        self.assertIsNotNone(declared.bot_standard_change(cfg, ctx("github-actions[bot]")))
        for lookalike in ("\uff47ithub-actions[bot]", "github-actions\u200b[bot]"):
            with self.subTest(lookalike=lookalike.encode("unicode_escape").decode()):
                self.assertIsNone(declared.bot_standard_change(cfg, ctx(lookalike)))

    def test_a_lookalike_of_an_approver_does_not_approve(self):
        from aidd.gate import inputs

        self.assertEqual(inputs.pool_members(["@checkout-lead"], {}), {"checkout-lead"})
        for lookalike in ("\uff43heckout-lead", "checkout\u200b-lead"):
            with self.subTest(lookalike=lookalike.encode("unicode_escape").decode()):
                self.assertNotIn(config.normalize_identity(lookalike), inputs.pool_members(["@checkout-lead"], {}))
                ctx = example(FEATURE)
                for item in (*ctx["reviews"], *ctx["comments"]):
                    if item.get("user") == "checkout-lead":
                        item["user"] = lookalike
                self.assertNotEqual(decide(ctx).decision, "pass")

    def test_bot_accounts_may_be_ignored(self):
        c = config.load_text(
            'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@x"]\nidentities:\n  system_accounts: [web-flow, "renovate[bot]"]\n'
        )
        self.assertEqual(c.get("identities", "system_accounts"), ["web-flow", "renovate[bot]"])
        self.assertEqual(c.warnings, [])


class StatusCheckSourceTests(unittest.TestCase):
    """Only check runs from an allowed app, on the PR's own branch, count; statuses never do."""

    def states(self, runs):
        client = github.Client("t", API, transport=FakeTransport({f"{API}/repos/o/r/commits/h/check-runs": ({}, {"check_runs": runs})}))
        return github._status_checks(client, "o/r", "h", ["build"], apps=["github-actions"], head_ref="feat")

    def check_run(self, conclusion, app="github-actions", branch="feat", started="2026-09-25T10:00:00Z"):
        return {
            "name": "build",
            "conclusion": conclusion,
            "status": "completed",
            "started_at": started,
            "app": {"slug": app},
            "check_suite": {"head_branch": branch},
        }

    def test_source_binding(self):
        self.assertEqual(self.states([self.check_run("success")]), {"build": "success"})
        self.assertEqual(self.states([self.check_run("success", app="evil-app")]), {})
        self.assertEqual(self.states([self.check_run("success", branch="decoy")]), {})

    def test_a_same_named_job_in_another_suite_cannot_hide_a_failure(self):
        failed = dict(self.check_run("failure", started="2026-09-25T09:00:00Z"), check_suite={"head_branch": "feat", "id": 1})
        decoy = dict(self.check_run("success", started="2026-09-25T11:00:00Z"), check_suite={"head_branch": "feat", "id": 2})
        self.assertEqual(self.states([failed, decoy]), {"build": "failure"})

    def test_a_rerun_in_the_same_suite_clears_a_failure(self):
        first = dict(self.check_run("failure", started="2026-09-25T09:00:00Z"), check_suite={"head_branch": "feat", "id": 1})
        rerun = dict(self.check_run("success", started="2026-09-25T11:00:00Z"), check_suite={"head_branch": "feat", "id": 1})
        self.assertEqual(self.states([first, rerun]), {"build": "success"})

    def test_newest_run_wins(self):
        runs = [self.check_run("success", started="2026-09-25T09:00:00Z"), self.check_run("failure", started="2026-09-25T11:00:00Z")]
        self.assertEqual(self.states(runs), {"build": "failure"})


class IncidentCloseOutTests(unittest.TestCase):
    """An emergency commits its backfill Spec, so `aidd validate` can hold the review debt."""

    def test_backfill_is_required_and_checked(self):
        ctx = example("05-emergency-under-freeze")
        self.assertEqual(decide(ctx).decision, "pass")
        broken = copy.deepcopy(ctx)
        del broken["head_files"]["specs/INC-481.md"]
        self.assertIn("emergency", rules(decide(broken), "fail"))
        missing = copy.deepcopy(ctx)
        inline(missing, "backfill: specs/INC-481.md\n", "")
        self.assertIn("change_request", rules(decide(missing), "fail"))


class ProtectedPathTests(unittest.TestCase):
    cfg = config.load_text('aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@x"]\n')

    def test_more_agent_and_ci_paths_are_protected(self):
        for path in (".kiro/steering/x.md", ".clinerules", ".windsurf/rules.md", "pkg/AGENT.md", "action.yml", ".tekton/p.yaml"):
            self.assertTrue(any(h.rule == "protected" for h in routing.scan([path], self.cfg)), path)

    def test_this_repository_protects_its_own_verifier(self):
        cfg = config.load_file(".aidd/config.yaml", str(ROOT))
        for path in ("src/aidd/gate/rules/__init__.py", "schemas/baseline.json", "templates/github/aidd-gate.yml", "action.yml"):
            self.assertTrue(any(h.rule == "protected" for h in routing.scan([path], cfg)), path)


class RulebookTests(unittest.TestCase):
    def test_every_emitted_rule_is_described(self):
        """The rule tables are generated from rulebook.RULES; it must cover every rule a gate can emit."""
        import re

        from aidd.gate import rulebook

        # Scan both files: `context` and `internal` are emitted by the gate's __init__.py, and a test that
        # hard-codes them cannot notice the fail-closed handler being deleted.
        source = package_source("aidd.gate.rules") + source_of("aidd.gate.engine")
        emitted = set(re.findall(r'add\("([a-z_]+)"', source))
        self.assertEqual(sorted(emitted - set(rulebook.BY_NAME)), [])
        self.assertIn("holds when", rulebook.explain_rule("scope"))
        # Every level a gate emits for a rule is named in that rule's row.
        for name, level in set(re.findall(r'add\("([a-z_]+)", "([a-z]+)"', source)):
            self.assertIn(level, rulebook.BY_NAME[name].levels, (name, level))

    def test_the_five_questions_hold_each_rule_once(self):
        """README and METHOD show the rules as five questions (`rules:questions`): a new rule must join one."""
        from aidd.gate import rulebook

        asked = [name for _, names in rulebook.QUESTIONS for name in names]
        self.assertEqual(len(rulebook.QUESTIONS), 5)
        self.assertEqual(sorted(asked), sorted(rulebook.BY_NAME))

    def test_the_gate_and_the_guard_read_one_explore_prefix(self):
        """The gate fails what the guard frees: both read the same branch prefix, kept apart only by the layers."""
        from aidd import workitems
        from aidd.gate.rules import route
        from aidd.guard import git_commands

        self.assertEqual({route.EXPLORE_PREFIX, git_commands.EXPLORE_PREFIX}, {workitems.EXPLORE_PREFIX})


class FailClosedTests(unittest.TestCase):
    """`internal` is the gate's central promise: a crash must never leave an older status standing.

    It is the one rulebook row whose emitter lives in the gate's __init__.py rather than gate/rules, so a sync test
    that scanned only gate/rules could never notice it being deleted. These assert the behavior.
    """

    def test_a_crashing_gate_fails_closed_under_the_internal_rule(self):
        ctx = example(FEATURE)

        def boom(run):
            raise RuntimeError("boom")

        with mock.patch.object(gates, "GATES", [boom]):
            d = decide(ctx)
        self.assertEqual(d.decision, "fail")
        self.assertEqual(rules(d, "fail"), ["internal"])
        self.assertEqual(rules(d, "pending"), [])
        self.assertIn("gate error", d.findings[0].message)
        self.assertIn("RuntimeError", d.findings[0].message)

    def test_the_record_still_carries_enough_to_post_a_status_after_a_crash(self):
        ctx = example(FEATURE)

        def boom(run):
            raise KeyError("head_sha")

        with mock.patch.object(gates, "GATES", [boom]):
            d = decide(ctx)
        self.assertEqual(d.record["decision"], "fail")
        self.assertEqual(d.record["head_sha"], ctx["head_sha"])
        self.assertEqual(d.record["change"], ctx["change"]["id"])

    def test_a_malformed_context_is_a_context_finding_not_a_crash(self):
        d = decide({"not": "a context"})
        self.assertEqual(d.decision, "fail")
        self.assertEqual(rules(d, "fail"), ["context"])
        self.assertEqual(rules(d, "fail") and d.rules_at("pending"), [])

    def test_both_fail_closed_rules_are_described_and_neither_is_hard_coded(self):
        source = package_source("aidd.gate.rules") + source_of("aidd.gate.engine")
        for name in ("context", "internal"):
            self.assertIn(f'add("{name}"', source, name)
            self.assertIn("holds when", rulebook.explain_rule(name))


if __name__ == "__main__":
    unittest.main()
