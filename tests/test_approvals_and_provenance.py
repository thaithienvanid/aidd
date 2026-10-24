"""Specialist pools, Co-authored-by provenance, minor-block defaults, the CLI verbs, and gate waits."""

import unittest

from helpers import adopted_repo, decide, example, rules
from helpers import run_cli as cli_run

from aidd import config
from aidd.cli import parser
from aidd.cli import arguments
from aidd.tracking import metrics
from aidd.gate import routing
from aidd.config.identities import agent_coauthors

FEATURE = "02-normal-feature"
MINOR = "01-minor-docs"
MAJOR = "04-major-permission"


def add_file(ctx, path, lines=3):
    ctx["files"].append({"path": path, "previous_path": None, "additions": lines, "deletions": 0, "binary": False})


class SpecialistPoolTests(unittest.TestCase):
    cfg = config.load_text('aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@x"]\n')

    def assess(self, paths, **kw):
        args = dict(cfg=self.cfg, ctype="feat", risk={"dimensions": [], "reversible": True}, confidence="high", task_count=1, changed_lines=10)
        args.update(kw)
        return routing.assess_route(paths=paths, **args)

    def test_each_reason_names_its_pool(self):
        self.assertEqual(self.assess(["db/migrations/1.sql"]).pools, {"data"})
        self.assertEqual(self.assess([".github/workflows/ci.yml"]).pools, {"security"})
        self.assertEqual(self.assess(["src/a.py"], risk={"dimensions": ["financial"], "reversible": True}).pools, {"finance"})
        self.assertEqual(self.assess(["src/a.py"], risk={"dimensions": ["privacy", "compliance"], "reversible": True}).pools, {"privacy", "compliance"})
        self.assertEqual(self.assess(["src/a.py"], ctype="data").pools, {"data"})
        self.assertEqual(self.assess(["src/a.py"], risk={"dimensions": [], "reversible": False}).pools, {"security"})
        self.assertEqual(self.assess(["docs/a.md"]).pools, set())
        self.assertEqual(self.assess(["docs/a.md"]).lane, "fast")

    def test_a_rule_may_name_its_own_pool(self):
        cfg = config.load_text(
            'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@x"]\n'
            'risk_rules:\n  - name: payments\n    paths: ["src/payments/**"]\n    route: major\n    dimensions: [financial]\n    specialists: [finance, risk_office]\n'
        )
        a = routing.assess_route(
            paths=["src/payments/charge.py"],
            cfg=cfg,
            ctype="feat",
            risk={"dimensions": [], "reversible": True},
            confidence="high",
            task_count=1,
            changed_lines=1,
        )
        self.assertEqual((a.required_route, a.pools), ("major", {"finance", "risk_office"}))

    def test_an_unbound_pool_falls_back_to_security(self):
        ctx = example(MAJOR)
        spec = ctx["head_files"]["specs/SPEC-221.md"]
        ctx["head_files"]["specs/SPEC-221.md"] = spec.replace("dimensions: [security]", "dimensions: [security, financial]")
        d = decide(ctx)
        self.assertEqual(sorted(d.record["required_pools"]), ["finance", "security"])
        self.assertNotIn("specialist_approval", rules(d, "pending"))  # the security pool's approval stands in for finance
        ctx["reviews"] = [r for r in ctx["reviews"] if r["user"] != "sec-alice"]
        d = decide(ctx)
        self.assertIn("specialist_approval", rules(d, "pending"))
        self.assertTrue(any("stands in" in f.message for f in d.findings if f.rule == "specialist_approval"), [f.message for f in d.findings])

    def test_each_named_pool_must_approve(self):
        ctx = example(MAJOR)
        ctx["base_config"] = ctx["base_config"].replace('    security: ["@sec-alice"]', '    security: ["@sec-alice"]\n    data: ["@dba"]')
        add_file(ctx, "db/migrations/0099_roles.sql")
        spec = ctx["head_files"]["specs/SPEC-221.md"]
        ctx["head_files"]["specs/SPEC-221.md"] = spec.replace("scope: [src/auth/]", "scope: [src/auth/, db/migrations/]")
        d = decide(ctx)
        self.assertIn("specialist_approval", rules(d, "pending"), [(f.rule, f.message) for f in d.findings])
        self.assertEqual(d.record["specialist_approved_by"]["data"], [])
        ctx["reviews"].append({"user": "dba", "state": "approved", "commit_sha": ctx["head_sha"], "submitted_at": "2026-09-23T09:50:00Z"})
        self.assertNotIn("specialist_approval", rules(decide(ctx), "pending"))

    def test_no_pool_at_all_fails_and_names_it(self):
        ctx = example(MAJOR)
        ctx["base_config"] = ctx["base_config"].replace('  specialists:\n    security: ["@sec-alice"]\n', "")
        d = decide(ctx)
        self.assertIn("specialist_approval", rules(d, "fail"))
        self.assertTrue(any("owners.specialists.security" in f.message for f in d.findings))

    def test_audited_pools_also_approve_the_spec(self):
        ctx = example(MAJOR)
        ctx["base_config"] = ctx["base_config"].replace("profile: team", "profile: audited")
        d = decide(ctx)
        msgs = [f.message for f in d.findings if f.rule == "specialist_approval"]
        self.assertTrue(any("needs a Spec approval from the security pool" in m for m in msgs), msgs)

    def test_init_reviewer_flag_parses_pools(self):
        self.assertEqual(arguments.specialists(["security=@org/sec,@alice", "data=@dba"]), {"security": ["@org/sec", "@alice"], "data": ["@dba"]})
        with self.assertRaises(ValueError):
            arguments.specialists(["security"])


class CoauthorProvenanceTests(unittest.TestCase):
    def test_known_agents_are_recognised(self):
        msg = "Fix\n\nCo-authored-by: Claude <noreply@anthropic.com>\nCo-authored-by: Bob Smith <bob@example.com>\nCo-authored-by: Copilot <198982749+Copilot@users.noreply.github.com>\n"
        self.assertEqual(agent_coauthors(msg), ["Claude <noreply@anthropic.com>", "Copilot <198982749+copilot@users.noreply.github.com>"])
        self.assertEqual(agent_coauthors("Co-authored-by: Jules Verne <jules@example.com>"), [])
        self.assertEqual(
            agent_coauthors("Co-authored-by: renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>"),
            ["renovate[bot] <29139614+renovate[bot]@users.noreply.github.com>"],
        )
        self.assertEqual(agent_coauthors("Co-authored-by: Corp Agent <agent@corp.example>", {"email:agent@corp.example"}), ["Corp Agent <agent@corp.example>"])

    def test_more_harnesses_are_recognised_by_name(self):
        # Codex is covered by both its name and its e-mail; the rest by name.
        self.assertEqual(
            agent_coauthors(
                "Co-authored-by: Codex <codex@openai.com>\nCo-authored-by: OpenCode <opencode@example.com>\n"
                "Co-authored-by: DeepSeek <deepseek@example.com>\nCo-authored-by: Antigravity <antigravity@example.com>\n"
                "Co-authored-by: Grok <grok@example.com>"
            ),
            [
                "Codex <codex@openai.com>",
                "OpenCode <opencode@example.com>",
                "DeepSeek <deepseek@example.com>",
                "Antigravity <antigravity@example.com>",
                "Grok <grok@example.com>",
            ],
        )

    def test_a_coauthored_commit_needs_assisted_by(self):
        ctx = example(MINOR)
        ctx["change"]["body"] = ctx["change"]["body"].replace("assisted_by: [claude-code/claude-opus-5-5]", "assisted_by: []")
        ctx["commits"][0]["message"] = "Fix typo\n\nCo-authored-by: Claude <noreply@anthropic.com>"
        d = decide(ctx)
        self.assertIn("provenance", rules(d, "fail"))
        self.assertTrue(any("Co-authored-by" in f.message for f in d.findings if f.rule == "provenance"))
        ctx["commits"][0]["message"] = "Fix typo\n\nCo-authored-by: Bob <bob@example.com>"
        self.assertNotIn("provenance", rules(decide(ctx), "fail"))

    def test_a_bot_author_needs_assisted_by(self):
        ctx = example(MINOR)
        ctx["change"]["body"] = ctx["change"]["body"].replace("assisted_by: [claude-code/claude-opus-5-5]", "assisted_by: []")
        ctx["commits"][0]["message"] = "Fix typo"
        ctx["commits"][0]["author"] = "claude[bot]"
        self.assertIn("provenance", rules(decide(ctx), "fail"))


class MinorDefaultsTests(unittest.TestCase):
    def test_three_lines_are_enough(self):
        ctx = example(MINOR)
        ctx["change"]["body"] = "```yaml aidd\nroute: minor\ntype: docs\nassisted_by: [claude-code/claude-opus-5-5]\n```\n"
        d = decide(ctx)
        self.assertEqual(d.decision, "pass", [(f.rule, f.message) for f in d.findings])
        self.assertEqual(
            (d.record["scope"], d.record["scope_declared"], d.record["confidence"], d.record["rollback"]),
            (["docs/guide.md"], False, "high", "Revert the change."),
        )

    def test_an_undeclared_scope_still_meets_every_other_rule(self):
        ctx = example(MINOR)
        ctx["change"]["body"] = "```yaml aidd\nroute: minor\nassisted_by: []\n```\n"
        add_file(ctx, "src/payments/refund.ts")
        d = decide(ctx)
        self.assertNotIn("scope", rules(d, "fail"))
        self.assertIn("provenance", rules(d, "fail"))  # the commit names an agent
        ctx = example(MINOR)
        ctx["change"]["body"] = "```yaml aidd\nroute: minor\nassisted_by: [claude-code/claude-opus-5-5]\n```\n"
        add_file(ctx, "db/migrations/0001.sql")
        self.assertIn("route", rules(decide(ctx), "fail"))

    def test_a_declared_scope_is_checked(self):
        ctx = example(MINOR)
        ctx["change"]["body"] = '```yaml aidd\nroute: minor\nscope: ["**"]\nassisted_by: [claude-code/claude-opus-5-5]\n```\n'
        self.assertIn("scope", rules(decide(ctx), "fail"))
        ctx["change"]["body"] = "```yaml aidd\nroute: minor\nscope: [docs/other.md]\nassisted_by: [claude-code/claude-opus-5-5]\n```\n"
        self.assertIn("scope", rules(decide(ctx), "fail"))

    def test_normal_without_a_spec_is_reported_under_spec(self):
        ctx = example(MINOR)
        ctx["change"]["body"] = "```yaml aidd\nroute: normal\nassisted_by: []\n```\n"
        d = decide(ctx)
        self.assertIn("spec", rules(d, "fail"))
        self.assertNotIn("change_request", rules(d, "fail"))


class CliVerbTests(unittest.TestCase):
    def test_gate_explains_a_rule(self):
        code, out = cli_run("gate", "--explain", "tests")
        self.assertEqual(code, 0)
        self.assertIn("holds when", out)
        self.assertEqual(cli_run("gate", "--explain", "checks")[0], 2)

    def test_old_verbs_are_gone(self):
        for verb in ("triage", "cr", "verify", "run-checks", "spec-hash", "check-repo"):
            with self.assertRaises(SystemExit):
                cli_run(verb)

    def test_planned_paths_report_the_lane_and_pools(self):
        from aidd import config

        cfg = config.load_text('aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@x"]\n')
        data = routing.route_summary(routing.assess_paths(cfg, ["db/migrations/1.sql"]), "planned paths")
        self.assertEqual((data["route"], data["lane"], data["pools"]), ("major", "spec", ["data"]))

    def test_gate_paths_forecasts_a_route_and_the_old_names_are_gone(self):
        with adopted_repo():
            code, out = cli_run("gate", "--paths", "db/migrations/1.sql")
        self.assertEqual(code, 0, out)
        self.assertIn("Route: major (spec lane)", out)
        for old in ("next", "assess"):
            self.assertNotIn(f"\n  {old} ", parser.build_parser().format_help())


class GateWaitTests(unittest.TestCase):
    def test_wait_per_gate_and_time_to_pass(self):
        base = {"repo": "acme/shop", "change": "7", "profile": "team", "failed_rules": []}
        events = [
            dict(base, ts="2026-09-25T10:00:00Z", decision="pending", pending_rules=["spec_approval", "tests"]),
            dict(base, ts="2026-09-25T10:30:00Z", decision="pending", pending_rules=["merge_approval"]),
            dict(base, ts="2026-09-25T12:00:00Z", decision="pass", pending_rules=[]),
            dict(base, change="8", ts="2026-09-25T09:00:00Z", decision="pending", pending_rules=["merge_approval"]),
        ]
        s = metrics.summarize_events(events)
        self.assertEqual(s["median_wait_minutes"], {"merge_approval": 90.0, "spec_approval": 30.0, "tests": 30.0})
        self.assertEqual(s["median_hours_to_pass"], 2.0)
        self.assertIn("Median wait per approval (minutes) | Merge approval 90.0, Spec approval 30.0", metrics.metrics_markdown(s))
        self.assertNotRegex(metrics.metrics_markdown(s), r"(per|by) gate|Gates above")
        # Flow: change 8 is still waiting on a human; one change passed inside a three-hour window (counted as a week's floor of one day).
        self.assertEqual((s["open_waiting"], s["open_waiting_by_rule"]), (1, {"merge_approval": 1}))
        self.assertEqual(s["throughput_per_week"], 7.0)
        self.assertEqual(s["wait_above_target"], {})
        self.assertEqual(metrics.summarize_events(events, target_wait_minutes=60)["wait_above_target"], {"merge_approval": 90.0})
        self.assertIn("Open changes waiting", metrics.metrics_markdown(s))


if __name__ == "__main__":
    unittest.main()
