"""Platform reuse: major as a computed overlay, CODEOWNERS, existing CI check runs as evidence, and observe-first init."""

import tempfile
import unittest
from pathlib import Path

from helpers import decide, example, rules

from aidd.setup import adoption
from aidd.gate import codeowners

FEATURE = "02-normal-feature"


def add_file(ctx, path):
    ctx["files"].append({"path": path, "previous_path": None, "additions": 3, "deletions": 0, "binary": False})


class OverlayTests(unittest.TestCase):
    def test_a_normal_spec_touching_auth_is_raised_not_failed(self):
        ctx = example(FEATURE)
        spec = ctx["head_files"]["specs/SPEC-220.md"]
        ctx["head_files"]["specs/SPEC-220.md"] = spec.replace("scope: [src/checkout/rate_limit/]", "scope: [src/checkout/rate_limit/, src/auth/]")
        add_file(ctx, "src/auth/session.ts")
        d = decide(ctx)
        self.assertEqual((d.record["route"], d.record["declared_route"]), ("major", "normal"))
        self.assertNotIn("route", rules(d, "fail"))
        self.assertIn("route", rules(d, "warn"))
        self.assertIn("specialist_approval", rules(d, "pending"))

    def test_a_minor_block_that_needs_a_spec_still_fails(self):
        d = decide(example("07-route-too-low"))
        self.assertIn("route", rules(d, "fail"))


class CodeownersTests(unittest.TestCase):
    def test_patterns_follow_gitignore_rules(self):
        cases = {
            "*.js": ["app.js", "src/deep/app.js"],
            "docs": ["docs/a.md", "x/docs/b.md"],
            "/build/logs/": ["build/logs/a.log"],
            "docs/*": ["docs/a.md"],
            "/src/app.py": ["src/app.py"],
        }
        for pattern, paths in cases.items():
            rules_ = codeowners.parse(f"{pattern} @o/t")
            for p in paths:
                self.assertEqual(codeowners.owners_for(rules_, p), ["@o/t"], (pattern, p))
        self.assertEqual(codeowners.owners_for(codeowners.parse("docs/* @o/t"), "docs/sub/a.md"), [])
        self.assertEqual(codeowners.owners_for(codeowners.parse("/build/ @o/t"), "src/build/x"), [])

    def test_last_match_wins_and_empty_owners_clear(self):
        text = "* @org/all\n/src/payments/ @org/payments\n/src/payments/generated/\n"
        r = codeowners.parse(text)
        self.assertEqual(codeowners.owners_for(r, "src/payments/charge.py"), ["@org/payments"])
        self.assertEqual(codeowners.owners_for(r, "src/payments/generated/x.py"), [])
        self.assertEqual(codeowners.owners_for(r, "README.md"), ["@org/all"])

    def test_codeowners_approval_is_required(self):
        ctx = example(FEATURE)
        ctx["base_config"] = ctx["base_config"].replace(
            'approvers: ["@checkout-lead", "@platform-lead", "@oncall-lead"]',
            'approvers: ["@checkout-lead", "@platform-lead", "@oncall-lead"]\n  codeowners: true',
        )
        ctx["codeowners"] = "/src/checkout/ @payments-lead\n"
        self.assertIn("merge_approval", rules(decide(ctx), "pending"))
        ctx["reviews"].append({"user": "payments-lead", "state": "approved", "commit_sha": ctx["head_sha"]})
        spec_ok = next(c for c in ctx["comments"] if "approve-spec" in c["body"])
        ctx["comments"].append({"user": "payments-lead", "body": spec_ok["body"]})
        d = decide(ctx)
        self.assertEqual(d.decision, "pass", [(f.rule, f.message) for f in d.findings])


class StatusCheckEvidenceTests(unittest.TestCase):
    def ctx(self, state):
        ctx = example(FEATURE)
        ctx["base_config"] += "\nevidence:\n  status_checks: [build]\n"
        ctx["status_checks"] = {} if state is None else {"build": state}
        return ctx

    def test_status_checks_count_as_evidence(self):
        self.assertEqual(decide(self.ctx("success")).decision, "pass")
        self.assertIn("tests", rules(decide(self.ctx(None)), "pending"))
        self.assertIn("tests", rules(decide(self.ctx("in_progress")), "pending"))
        self.assertIn("tests", rules(decide(self.ctx("failure")), "fail"))


class ObserveFirstTests(unittest.TestCase):
    def test_init_starts_advisory_unless_enforced(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            adoption.init(root, adoption.InitOptions(profile="solo", ci="github", links=[], skill=False, approvers=["@me"]))
            self.assertIn("mode: advisory", (root / ".github/workflows/aidd-gate.yml").read_text(encoding="utf-8"))
            self.assertIn("\nmode: advisory", (root / ".aidd/config.yaml").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            adoption.init(root, adoption.InitOptions(profile="solo", ci="gitlab", links=[], skill=False, enforce=True, approvers=["@me"]))
            # GitLab reads the mode from the base branch's config; the CI file carries no AIDD_MODE to override.
            self.assertIn("\nmode: enforce", (root / ".aidd/config.yaml").read_text(encoding="utf-8"))
            self.assertNotIn("AIDD_MODE", (root / ".gitlab/aidd.gitlab-ci.yml").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            adoption.init(root, adoption.InitOptions(profile="solo", ci="gitlab", links=[], skill=False, approvers=["@me"]))
            self.assertIn("\nmode: advisory", (root / ".aidd/config.yaml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
