"""Approval, emergency, evidence, path, and config hardening: each test was a way to get a wrong pass."""

import time
import unittest

from helpers import decide, example, rules

from aidd import config, globs, model

FEATURE = "02-normal-feature"


def add_file(ctx, path, a=5, d=0, binary=False):
    ctx["files"].append({"path": path, "previous_path": None, "additions": a, "deletions": d, "binary": binary})


def spec_approval(ctx):
    return next(c for c in ctx["comments"] if "approve-spec" in c["body"])


class ApprovalHardeningTests(unittest.TestCase):
    def assertHeld(self, d, rule, level="pending"):
        self.assertIn(rule, rules(d, level), [(f.rule, f.level, f.message) for f in d.findings])
        self.assertNotEqual(d.decision, "pass")

    def test_comment_approval_does_not_count_outside_solo(self):
        ctx = example(FEATURE)
        ctx["reviews"] = []
        ctx["comments"].append({"user": "checkout-lead", "body": f"/aidd approve {ctx['head_sha']}"})
        self.assertHeld(decide(ctx), "merge_approval")

    def test_solo_comment_approval_needs_the_full_sha(self):
        ctx = example("11-solo-major")
        for form in ("approve-merge", "approve"):
            ctx["comments"][1]["body"] = f"/aidd {form} {ctx['head_sha'][:7]}"
            self.assertHeld(decide(ctx), "merge_approval")

    def test_solo_merge_approval_is_approve_merge_and_the_earlier_form_still_counts(self):
        ctx = example("11-solo-major")
        self.assertEqual(ctx["comments"][1]["body"], f"/aidd approve-merge {ctx['head_sha']}")  # the documented form
        self.assertNotIn("merge_approval", rules(decide(ctx), "pending") + rules(decide(ctx), "fail"))
        ctx["comments"][1]["body"] = f"/aidd approve {ctx['head_sha']}"  # adopters' earlier form
        self.assertNotIn("merge_approval", rules(decide(ctx), "pending") + rules(decide(ctx), "fail"))

    def test_edited_comments_never_approve(self):
        ctx = example(FEATURE)
        spec_approval(ctx)["edited"] = True
        d = decide(ctx)
        self.assertHeld(d, "spec_approval")
        self.assertIn("edited_comments", rules(d, "warn"))

    def test_quoted_or_fenced_commands_do_not_count(self):
        for wrap in ("> {}", "```\n{}\n```", "~~~\n{}\n~~~"):
            ctx = example(FEATURE)
            c = spec_approval(ctx)
            c["body"] = wrap.format(c["body"])
            self.assertHeld(decide(ctx), "spec_approval")

    def test_empty_approvers_is_a_config_error_outside_solo(self):
        ctx = example(FEATURE)
        ctx["base_config"] = ctx["base_config"].replace('approvers = ["@checkout-lead", "@platform-lead", "@oncall-lead"]', "approvers = []")
        self.assertHeld(decide(ctx), "config", "fail")

    def test_solo_empty_approvers_means_only_the_author(self):
        ctx = example("11-solo-major")
        ctx["comments"][1]["user"] = "drive-by-stranger"
        self.assertHeld(decide(ctx), "merge_approval")

    def test_bots_approve_only_when_named(self):
        ctx = example(FEATURE)
        ctx["base_config"] = ctx["base_config"].replace('approvers = ["@checkout-lead", "@platform-lead", "@oncall-lead"]', 'approvers = ["@acme/leads"]')
        ctx["team_members"] = {"@acme/leads": ["checkout-lead", "review-bot[bot]"]}
        ctx["reviews"] = [{"user": "review-bot[bot]", "state": "approved", "commit_sha": ctx["head_sha"]}]
        self.assertHeld(decide(ctx), "merge_approval")

    def test_spec_approvers_only_narrow_the_config(self):
        ctx = example(FEATURE)
        spec = ctx["head_files"]["specs/SPEC-220.md"].replace('owner_team = "checkout"', 'owner_team = "checkout"\napprovers = ["mallory"]')
        ctx["head_files"]["specs/SPEC-220.md"] = spec
        h = model.spec_hash(spec, ctx["head_tree"])
        ctx["comments"] = [{"user": "mallory", "body": f"/aidd approve-spec SPEC-220 {h}"}]
        ctx["reviews"] = [{"user": "mallory", "state": "approved", "commit_sha": ctx["head_sha"]}]
        d = decide(ctx)
        self.assertHeld(d, "spec_approval")
        self.assertHeld(d, "merge_approval")

    def test_a_later_comment_review_does_not_clear_changes_requested(self):
        ctx = example(FEATURE)
        ctx["reviews"] += [
            {"user": "platform-lead", "state": "changes_requested", "commit_sha": ctx["head_sha"], "submitted_at": "2026-09-23T09:40:00Z"},
            {"user": "platform-lead", "state": "commented", "commit_sha": ctx["head_sha"], "submitted_at": "2026-09-23T09:50:00Z"},
        ]
        self.assertHeld(decide(ctx), "merge_approval")

    def test_stricter_standard_approvals_apply(self):
        ctx = example("06-standard-dependency")
        ctx["base_config"] += "\n[gates]\napprovals = { standard = 1 }\n"
        self.assertHeld(decide(ctx), "merge_approval")

    def test_standard_change_needs_signed_commits(self):
        ctx = example("06-standard-dependency")
        ctx["commits"][0]["verified"] = False
        self.assertHeld(decide(ctx), "standard_change", "fail")

    def test_truncated_commit_list_fails(self):
        ctx = example(FEATURE)
        ctx["commits_truncated"] = True
        self.assertHeld(decide(ctx), "authors", "fail")

    def test_system_accounts_never_hide_the_change_author(self):
        ctx = example(FEATURE)
        ctx["base_config"] = ctx["base_config"].replace('system_accounts = ["web-flow"]', 'system_accounts = ["web-flow", "alice"]')
        ctx["reviews"] = [{"user": "alice", "state": "approved", "commit_sha": ctx["head_sha"]}]
        self.assertHeld(decide(ctx), "merge_approval")


class EmergencyHardeningTests(unittest.TestCase):
    def test_emergency_touching_protected_paths_keeps_specialist_approval(self):
        ctx = example("05-emergency-under-freeze")
        ctx["change"]["body"] = ctx["change"]["body"].replace('scope = ["src/auth/session.ts"]', 'scope = ["src/auth/session.ts", ".github/"]')
        add_file(ctx, ".github/workflows/deploy.yml")
        ctx["reviews"] = [r for r in ctx["reviews"] if r["user"] != "sec-alice"]  # only the commander approved
        d = decide(ctx)
        self.assertIn("specialist_approval", rules(d, "pending"))

    def test_commander_must_approve_and_not_be_an_author(self):
        ctx = example("05-emergency-under-freeze")
        ctx["reviews"] = [{"user": "identity-lead", "state": "approved", "commit_sha": ctx["head_sha"]}]
        self.assertIn("emergency", rules(decide(ctx), "pending"))
        ctx = example("05-emergency-under-freeze")
        ctx["change"]["body"] = ctx["change"]["body"].replace('commander = "@oncall-lead"', 'commander = "@bob"')
        self.assertIn("emergency", rules(decide(ctx), "fail"))

    def test_review_due_in_the_past_or_impossible(self):
        for due in ("2026-09-01", "2026-02-30"):
            ctx = example("05-emergency-under-freeze")
            ctx["change"]["body"] = ctx["change"]["body"].replace("review_due = 2026-09-24", f'review_due = "{due}"')
            d = decide(ctx)
            failed = rules(d, "fail")
            self.assertTrue("emergency" in failed or "change_request" in failed, [(f.rule, f.message) for f in d.findings])


class EvidenceHardeningTests(unittest.TestCase):
    def test_evidence_from_another_base_is_held(self):
        ctx = example(FEATURE)
        ctx["evidence"]["base_sha"] = "c" * 40
        self.assertIn("tests", rules(decide(ctx), "pending"))

    def test_red_run_must_use_the_declared_command(self):
        ctx = example(FEATURE)
        for r in ctx["evidence"]["results"]:
            if r["red_green"] == "red":
                r["command"] = ["false"]
        self.assertIn("red_green", rules(decide(ctx), "fail"))

    def test_malformed_context_fails_closed(self):
        ctx = example(FEATURE)
        del ctx["files"]
        self.assertIn("context", rules(decide(ctx), "fail"))


class PathHardeningTests(unittest.TestCase):
    cfg = config.load_text('aidd_version = "1.0.0"\nprofile = "team"\n[owners]\napprovers = ["@x"]\n')

    def test_dir_star_star_covers_the_dir_itself(self):
        self.assertTrue(globs.match(".claude/**", ".claude"))
        self.assertTrue(globs.match(".github/actions/**", ".github/actions"))

    def test_protected_paths_ignore_case_and_newlines(self):
        from aidd import rules as r

        for path in (".Claude/settings.json", "docs/claude.md", "sub\ndir/AGENTS.md", ".claude"):
            hits = r.scan([path], self.cfg)
            self.assertTrue(any(h.rule == "protected" for h in hits), path)

    def test_brackets_are_literal(self):
        self.assertTrue(globs.match("app/[tenant]", "app/[tenant]/page.tsx"))

    def test_pathological_patterns_stay_fast(self):
        t = time.monotonic()
        globs.match("**/" * 30 + "zz", "a/" * 40 + "b")
        self.assertLess(time.monotonic() - t, 2.0)

    def test_binary_files_are_not_minor(self):
        ctx = example("01-minor-docs")
        ctx["files"] = [{"path": "docs/guide.md", "previous_path": None, "additions": 0, "deletions": 0, "binary": True}]
        self.assertIn("route", rules(decide(ctx), "fail"))


class ConfigHardeningTests(unittest.TestCase):
    def test_parent_owned_settings_cannot_be_replaced(self):
        parent = (
            'aidd_version = "1.0.0"\nprofile = "org"\n[owners.specialists]\nsecurity = ["@org/security"]\n'
            '[policy]\ncommand = ["org-policy"]\n[identities]\nsystem_accounts = ["web-flow"]\nbots = ["bot-a"]\n[emergency]\nreview_sla_days = 2\n'
        )
        child = (
            'aidd_version = "1.0.0"\nprofile = "org"\nextends = [{ path = "p.toml" }]\n[owners.specialists]\nsecurity = ["@me"]\ndata = ["@dba"]\n'
            '[policy]\ncommand = ["true"]\n[identities]\nsystem_accounts = ["alice"]\nbots = ["bot-b"]\n[emergency]\nreview_sla_days = 30\n'
        )
        c = config.load_text(child, prefetched={"p.toml": parent})
        self.assertEqual(c.specialists, {"security": ["@org/security"], "data": ["@dba"]})
        self.assertEqual(c.policy_command, ["org-policy"])
        self.assertEqual(c.get("identities", "system_accounts"), ["web-flow"])
        self.assertEqual(c.get("identities", "bots"), ["bot-a", "bot-b"])
        self.assertEqual(c.get("emergency", "review_sla_days"), 2)
        self.assertEqual(len([w for w in c.warnings if "cannot be replaced" in w or "cannot add" in w]), 3)

    def test_spec_hash_is_128_bits(self):
        spec = (example(FEATURE))["head_files"]["specs/SPEC-220.md"]
        self.assertEqual(len(model.spec_hash(spec, {})), 32)


if __name__ == "__main__":
    unittest.main()
