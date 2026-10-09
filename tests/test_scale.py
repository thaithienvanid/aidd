"""Scale and adoption features: bot standard changes, per-path owners, per-path tests, presets, CLI robustness."""

import contextlib
import io
import os
import shutil
import subprocess
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from helpers import decide, example, rules
from helpers import run_cli as cli_run

from aidd import config, github, http, inputs, model
from aidd import rules as aidd_rules

FEATURE = "02-normal-feature"
OWNERS = '\n[[owners.paths]]\npaths = ["src/checkout/**"]\napprovers = ["@checkout-owner"]\n'


class BotStandardChangeTests(unittest.TestCase):
    def test_bot_pr_without_block_matches_its_class(self):
        ctx = example("06-standard-dependency")
        ctx["change"]["body"] = "Bumps left-pad from 1.3.0 to 1.3.1."
        d = decide(ctx)
        self.assertEqual(d.decision, "pass", [(f.rule, f.message) for f in d.findings])
        self.assertIn("change_request", rules(d, "warn"))

    def test_human_pr_without_block_still_fails(self):
        ctx = example("06-standard-dependency")
        ctx["change"]["body"] = "Bump"
        ctx["change"]["author"] = "alice"
        self.assertIn("change_request", rules(decide(ctx), "fail"))


class ProposalBudgetTests(unittest.TestCase):
    def ctx(self, paths):
        ctx = example("01-minor-docs")
        ctx["files"] = [{"path": p, "previous_path": None, "additions": 300, "deletions": 0} for p in paths]
        scope = "scope = [" + ", ".join(f'"{p}"' for p in paths) + "]"
        ctx["change"]["body"] = ctx["change"]["body"].replace('scope = ["docs/guide.md"]', scope)
        return ctx

    def test_proposal_only_change_is_not_counted(self):
        d = decide(self.ctx(["proposals/PROP-1/proposal.md", "proposals/PROP-1/security.md"]))
        self.assertNotIn("budget", rules(d, "fail"))

    def test_mixed_change_counts_in_full(self):
        d = decide(self.ctx(["proposals/PROP-1/proposal.md", "docs/guide.md"]))
        self.assertIn("budget", rules(d, "fail"))


class DocumentRouteTests(unittest.TestCase):
    """In a proposal-only change, a baseline rule does not match a binary document by path, and the document does not
    count as a binary. Code, text, other binaries, protected paths, dependencies, and every change outside route as before."""

    def setUp(self):
        self.cfg = config.load_text('aidd_version = "1.0.0"\nprofile = "team"\n[owners]\napprovers = ["@x"]\n')

    def route(self, files, cfg=None, **kw):
        files = [{"path": p, "previous_path": None, "additions": 0, "deletions": 0, "binary": binary} for p, binary in files]
        return aidd_rules.assess(
            paths=aidd_rules.changed_paths(files),
            cfg=cfg or self.cfg,
            ctype="docs",
            risk={"dimensions": [], "reversible": True},
            confidence="high",
            task_count=1,
            changed_lines=0,
            binary_files=aidd_rules.counted_binaries(files, cfg or self.cfg),
            binary_paths=aidd_rules.binary_paths(files),
            **kw,
        )

    def test_a_text_file_named_as_a_document_still_matches(self):
        # git sees text, so the name alone does not make it a document: baseline:auth still applies.
        a = self.route([("proposals/P/auth/handler.pdf", False)])
        self.assertEqual(a.required_route, "major", a.reasons)
        self.assertIn("baseline:auth", {h.rule for h in a.hits})

    def test_a_security_document_in_a_proposal_stays_minor(self):
        a = self.route([("proposals/P/share/security.docx", True)])
        self.assertEqual((a.required_route, a.dimensions), ("minor", set()), a.reasons)

    def test_code_and_text_in_a_proposal_still_match_their_rules(self):
        for path, rule in (
            ("proposals/P/data/auth.py", "baseline:auth"),
            ("proposals/P/secrets/notes.txt", "baseline:secrets-crypto"),
            ("proposals/P/customers.csv", "baseline:personal-data"),
        ):
            a = self.route([(path, False)])
            self.assertEqual(a.required_route, "major", path)
            self.assertIn(rule, {h.rule for h in a.hits}, path)

    def test_personal_data_in_a_proposal_document_still_matches(self):
        a = self.route([("proposals/P/customers/customers.xlsx", True)])
        self.assertEqual(a.required_route, "major", a.reasons)
        self.assertIn("privacy", a.dimensions)
        self.assertIn("baseline:personal-data", {h.rule for h in a.hits})
        self.assertNotIn("baseline:personal-data", aidd_rules.LOGIC_RULES)

    def test_a_binary_that_is_not_a_document_still_counts_in_a_proposal(self):
        self.assertEqual(self.route([("proposals/P/tool.bin", True)]).required_route, "normal")
        self.assertEqual(self.route([("proposals/P/a.docx", True), ("proposals/P/tool.bin", True)]).required_route, "normal")

    def test_outside_a_proposal_only_change_every_rule_matches_as_before(self):
        self.assertEqual(self.route([("docs/report.pdf", True)]).required_route, "normal")  # the binary counts
        for files in ([("src/security.docx", False)], [("proposals/P/security.docx", True), ("docs/b.md", False)]):
            a = self.route(files)
            self.assertEqual(a.required_route, "major", files)
            self.assertIn("baseline:auth", {h.rule for h in a.hits}, files)
        self.assertEqual(aidd_rules.assess_paths(self.cfg, ["secrets/prod.txt"]).required_route, "major")
        self.assertEqual(aidd_rules.assess_paths(self.cfg, ["src/auth/login.py"]).required_route, "major")

    def test_protected_paths_dependencies_and_config_rules_still_apply_in_a_proposal(self):
        self.assertEqual(aidd_rules.assess_paths(self.cfg, ["proposals/P/AGENTS.md"]).required_route, "major")
        deps = [{"file": "proposals/P/package.json", "name": "next-auth"}]
        self.assertEqual(self.route([("proposals/P/package.json", False)], dependencies=deps).required_route, "major")
        own = '\n[[risk_rules]]\nname = "contracts"\nroute = "major"\ndimensions = ["compliance"]\npaths = ["**/contracts/**"]\n'
        cfg = config.load_text('aidd_version = "1.0.0"\nprofile = "team"\n[owners]\napprovers = ["@x"]\n' + own)
        self.assertEqual(self.route([("proposals/P/contracts/msa.pdf", True)], cfg=cfg).required_route, "major")

    def test_the_gate_agrees(self):
        def ctx(files):
            c = ProposalBudgetTests.ctx(self, [p for p, _ in files])
            for f, (_, binary) in zip(c["files"], files, strict=True):
                f["binary"] = binary
            return c

        d = decide(ctx([("proposals/P/share/security.docx", True)]))
        self.assertEqual(d.decision, "pass", [(f.rule, f.message) for f in d.findings])
        self.assertIn("route", rules(decide(ctx([("proposals/P/tool.bin", True)])), "fail"))
        self.assertIn("route", rules(decide(ctx([("proposals/P/data/auth.py", False)])), "fail"))


class PerPathOwnerTests(unittest.TestCase):
    def ctx(self):
        ctx = example(FEATURE)
        ctx["base_config"] = ctx["base_config"].replace("[[tests]]", OWNERS.lstrip("\n") + "\n[[tests]]", 1)
        return ctx

    def test_path_owner_must_approve_spec_and_ship(self):
        d = decide(self.ctx())
        self.assertIn("spec_approval", rules(d, "pending"))
        self.assertIn("merge_approval", rules(d, "pending"))

    def test_path_owner_approval_passes(self):
        ctx = self.ctx()
        h = model.spec_hash(ctx["head_files"]["specs/SPEC-220.md"], ctx["head_tree"])
        ctx["comments"].append({"user": "checkout-owner", "body": f"/aidd approve-spec SPEC-220 {h}"})
        ctx["reviews"].append({"user": "checkout-owner", "state": "approved", "commit_sha": ctx["head_sha"]})
        d = decide(ctx)
        self.assertEqual(d.decision, "pass", [(f.rule, f.message) for f in d.findings])


class TestSelectionTests(unittest.TestCase):
    def test_when_changed_applies_only_to_matching_paths(self):
        extra = '\n[[tests]]\nname = "docs-lint"\ncommand = ["make", "docs"]\nwhen_changed = ["docs/**"]\n'
        ctx = example(FEATURE)
        ctx["base_config"] += extra
        self.assertEqual(decide(ctx).decision, "pass")
        ctx = example("01-minor-docs")
        ctx["base_config"] += extra
        self.assertIn("tests", rules(decide(ctx), "fail"))

    def test_duplicate_test_names_fail(self):
        ctx = example(FEATURE)
        ctx["base_config"] += '\n[[tests]]\nname = "rate-limit"\ncommand = ["true"]\n'
        self.assertIn("tests", rules(decide(ctx), "fail"))


class PathRuleTests(unittest.TestCase):
    def cfg(self, extra=""):
        return config.load_text('aidd_version = "1.0.0"\nprofile = "team"\n' + extra + '\n[owners]\napprovers = ["@x"]\n')

    def route(self, path, extra=""):
        return aidd_rules.assess(
            paths=[path], cfg=self.cfg(extra), ctype="feat", risk={"dimensions": [], "reversible": True}, confidence="high", task_count=1, changed_lines=1
        ).required_route

    def test_policy_script_is_protected(self):
        self.assertEqual(self.route("scripts/aidd-policy", '[policy]\ncommand = ["./scripts/aidd-policy"]\n'), "major")
        self.assertEqual(self.route("scripts/other"), "minor")

    def test_rules_ignore_case_and_honor_exceptions(self):
        self.assertEqual(self.route("src/Data/Migrations/0001_init.cs"), "major")
        self.assertEqual(self.route("web/components/auth/Login.tsx"), "major")
        self.assertEqual(self.route("web/components/auth/Login.tsx", 'rule_exclusions = { "baseline:auth" = ["web/**"] }\n'), "minor")
        self.assertEqual(self.route(".env.example"), "minor")
        self.assertEqual(self.route("vendor/golang.org/x/crypto/a.go"), "minor")

    def test_new_third_party_and_ci_paths(self):
        for path in (".npmrc", "gradle/wrapper/gradle-wrapper.properties", "Makefile", ".terraform.lock.hcl"):
            self.assertEqual(self.route(path), "normal", path)
        for path in (".github/dependabot.yml", "renovate.json", "Jenkinsfile", ".circleci/config.yml"):
            self.assertEqual(self.route(path), "major", path)


class PresetTests(unittest.TestCase):
    def test_nested_extends_resolve_through_verify(self):
        files = {
            "a.toml": 'aidd_version = "1.0.0"\nprofile = "team"\nextends = [{ path = "b.toml" }]\n',
            "b.toml": 'aidd_version = "1.0.0"\nprofile = "team"\nprotected_paths = ["infra/**"]\n',
        }
        ctx = example(FEATURE)
        ctx["base_config"] = ctx["base_config"].replace('profile = "team"', 'profile = "team"\nextends = [{ path = "a.toml" }]')
        ctx["extends_texts"] = inputs.collect_extends(ctx["base_config"], files.get)
        self.assertEqual(sorted(ctx["extends_texts"]), ["a.toml", "b.toml"])
        self.assertEqual(decide(ctx).decision, "pass")

    def test_org_preset_is_the_root_parent(self):
        ctx = example("04-major-permission")
        ctx["org_preset"] = 'aidd_version = "1.0.0"\nprofile = "team"\n[gates]\npolicy_required_routes = ["major"]\n'
        self.assertIn("policy", rules(decide(ctx), "fail"))

    def test_repo_cannot_be_weaker_than_the_org_preset(self):
        ctx = example("04-major-permission")
        ctx["org_preset"] = 'aidd_version = "1.0.0"\nprofile = "org"\n'
        self.assertIn("config", rules(decide(ctx), "fail"))

    def test_advisory_status_never_satisfies_the_rule(self):
        self.assertEqual(github.status_context("main", ["main"], "advisory"), "aidd/gate (advisory)")
        self.assertEqual(github.status_context("release/2.0", ["main", "release/*"]), "aidd/gate")


class HttpTests(unittest.TestCase):
    def test_rate_limit_is_retried(self):
        calls = []

        class Resp(io.BytesIO):
            status = 200
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake(req, timeout=30):
            calls.append(req.full_url)
            if len(calls) == 1:
                raise urllib.error.HTTPError(req.full_url, 429, "slow down", {"Retry-After": "1"}, io.BytesIO(b"{}"))
            return Resp(b'{"ok": true}')

        with mock.patch.object(http._OPENER, "open", fake), mock.patch("time.sleep"):
            self.assertEqual(http.get_bytes("https://api.test/x"), b'{"ok": true}')
        self.assertEqual(len(calls), 2)

    def test_network_errors_become_http_errors(self):
        def fake(req, timeout=30):
            raise urllib.error.URLError("no route")

        with mock.patch.object(http._OPENER, "open", fake), mock.patch("time.sleep"):
            with self.assertRaises(http.HttpError):
                http.get_bytes("https://api.test/x")


@unittest.skipUnless(shutil.which("git"), "git is required")
class CliRobustnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)  # after a test's chdir is undone: Windows cannot remove the working directory
        self.root = Path(self.tmp.name)
        run = lambda *a: subprocess.run(["git", *a], cwd=self.root, check=True, capture_output=True)  # noqa: E731
        run("init", "-q", "-b", "master")
        run("config", "user.email", "a@example.com")
        run("config", "user.name", "A")
        run("config", "commit.gpgsign", "false")
        (self.root / ".aidd").mkdir()
        (self.root / ".aidd/config.toml").write_text('aidd_version = "1.0.0"\nprofile = "solo"\n', encoding="utf-8")
        (self.root / "docs").mkdir()
        (self.root / "docs/a.md").write_text("a\n", encoding="utf-8")
        run("add", ".")
        run("commit", "-qm", "base")
        run("checkout", "-qb", "feature")
        (self.root / "docs/a.md").write_text("b\n", encoding="utf-8")
        run("commit", "-qam", "edit")

    def test_default_base_and_subdirectory(self):
        self.enterContext(contextlib.chdir(self.root / "docs"))
        route = aidd_rules.assess_diff(self.root)  # what `aidd assess` shows for the branch
        self.assertIsNotNone(route)
        self.assertIn("diff against master", route["basis"])
        self.assertEqual((route["paths"], route["route"]), (["docs/a.md"], "minor"))
        code, out = cli_run("describe")
        self.assertEqual(code, 0, out)
        self.assertIn('scope = ["docs/a.md"]', out)
        self.assertIn('type = "docs"', out)

    def test_assess_and_the_gate_decide_proposal_only_from_the_same_paths(self):
        """A committed binary document in a proposal plus an uncommitted code edit: not proposal-only, so the document counts."""
        run = lambda *a: subprocess.run(["git", *a], cwd=self.root, check=True, capture_output=True)  # noqa: E731
        run("checkout", "-qb", "bid", "master")
        (self.root / "proposals/P").mkdir(parents=True)
        (self.root / "proposals/P/a.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00binary")
        run("add", ".")
        run("commit", "-qm", "picture")
        self.assertEqual(aidd_rules.assess_diff(self.root)["route"], "minor")  # proposal-only: the picture does not count
        (self.root / "src").mkdir()
        (self.root / "src/x.py").write_text("x = 1\n", encoding="utf-8")  # untracked, not committed
        route = aidd_rules.assess_diff(self.root)
        files = [{"path": "proposals/P/a.png", "previous_path": None, "additions": 0, "deletions": 0, "binary": True}]
        files.append({"path": "src/x.py", "previous_path": None, "additions": 1, "deletions": 0})
        self.assertEqual(aidd_rules.counted_binaries(files, config.load_file(config.CONFIG_PATH, str(self.root))), 1)
        self.assertEqual(route["route"], "normal", route["reasons"])  # what the gate computes for the pushed change

    def test_proposal_only_branch_needs_no_spec(self):
        run = lambda *a: subprocess.run(["git", *a], cwd=self.root, check=True, capture_output=True)  # noqa: E731
        run("checkout", "-qb", "bid", "master")
        (self.root / "proposals/PROP-1").mkdir(parents=True)
        (self.root / "proposals/PROP-1/proposal.md").write_text("line\n" * 400, encoding="utf-8")
        run("add", ".")
        run("commit", "-qm", "proposal")
        route = aidd_rules.assess_diff(self.root)
        self.assertEqual((route["route"], route["changed_lines"]), ("minor", 0))
        self.assertTrue(any("proposal-only" in r for r in route["reasons"]), route["reasons"])
        (self.root / "docs/a.md").write_text("c\n" * 400, encoding="utf-8")  # anything else counts in full
        route = aidd_rules.assess_diff(self.root)
        self.assertEqual(route["route"], "normal")
        self.assertFalse(any("proposal-only" in r for r in route["reasons"]), route["reasons"])

    def test_errors_exit_two(self):
        bad = self.root / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        self.assertEqual(cli_run("gate", "--context", str(bad))[0], 2)
        self.assertEqual(cli_run("new", "spec", "../escape", "--title", "x")[0], 2)
        with mock.patch.dict(os.environ, {"GITHUB_REPOSITORY": ""}):
            self.assertEqual(cli_run("gate", "github")[0], 2)


if __name__ == "__main__":
    unittest.main()
