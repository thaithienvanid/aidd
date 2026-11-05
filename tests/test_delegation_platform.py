"""The delegate check's GitHub reads: what `gh api` answers, read only, through a stand-in `gh` that answers from files,
and the gates of a merge and a push on those answers. Nothing reaches the network."""

import json
import os
import shlex
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import git, write_executable
from test_delegation_check import ENV, FakeGitHub, Repo, codes, note

from aidd.delegation import platform

STUB_CODE = """import json, os, sys
path = sys.argv[-1]
answers = json.load(open(os.environ["STUB_ANSWERS"]))
if path not in answers:
    print("gh: Not Found (HTTP 404)", file=sys.stderr)
    sys.exit(1)
print(json.dumps(answers[path]))
"""
# A `#!/bin/sh` stub, so `write_executable` makes it a link to the one shared launcher, that runs this interpreter by its
# path, never a `python3` that PATH finds first, such as a version manager's shim that starts a shell.
STUB = f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -c {shlex.quote(STUB_CODE)} "$@"\n'

WORKFLOW = "name: aidd-tests\non:\n  pull_request:\njobs:\n  tests:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: thaithienvanid/aidd@v1.0.0\n"
RULES = {"required_checks": ["tests"], "strict": False, "blocks_force_push": True, "blocks_deletion": True}


class StubGhTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        write_executable(self.dir / "gh", STUB)

    def tearDown(self):
        self.tmp.cleanup()

    def reader(self, answers: dict) -> platform.GitHub:
        (self.dir / "answers.json").write_text(json.dumps(answers), encoding="utf-8")
        env = {"PATH": f"{self.dir}{os.pathsep}{os.environ.get('PATH', '')}", "STUB_ANSWERS": str(self.dir / "answers.json"), "GH_REPO": "evil/other"}
        return platform.GitHub("acme/shop", str(self.dir), env)

    def test_the_reads_parse_and_a_missing_page_is_none(self):
        gh = self.reader(
            {
                "repos/acme/shop": {"default_branch": "main"},
                "repos/acme/shop/branches/main": {"commit": {"sha": "a" * 40}},
                "repos/acme/shop/rules/branches/main": [
                    {"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "tests"}]}},
                    {"type": "non_fast_forward"},
                    {"type": "deletion"},
                ],
            }
        )
        self.assertNotIn("GH_REPO", gh.env, "no variable steers gh at another repository")
        self.assertEqual((gh.default_branch(), gh.branch_tip("main")), ("main", "a" * 40))
        self.assertEqual({k: v for k, v in gh.rules("main").items() if k not in ("readable", "bypass")}, RULES)
        self.assertFalse(gh.rules("main")["bypass"])
        self.assertIsNone(gh.pages_branch())
        with self.assertRaises(platform.PlatformError):
            gh.pull(12)

    def test_check_requires_the_ci_check_on_the_head(self):
        head, wf = "b" * 40, ".github/workflows/aidd-tests.yml"
        ours = {
            "id": 30,
            "check_suite_id": 3,
            "path": wf,
            "event": "pull_request",
            "created_at": "2026-11-08T10:00:00Z",
            "pull_requests": [{"number": 12, "base": {"ref": "main"}}],
        }

        def check(app="github-actions", sha=head, conclusion="success", runs=(ours,)):
            return {
                f"repos/acme/shop/commits/{head}/check-runs?check_name=tests&per_page=100": {
                    "check_runs": [{"id": 7, "app": {"slug": app}, "head_sha": sha, "conclusion": conclusion, "check_suite": {"id": 3}}]
                },
                f"repos/acme/shop/actions/runs?head_sha={head}&per_page=100": {"workflow_runs": list(runs)},
            }

        self.assertEqual(self.reader(check()).tests_run(head, wf, 12, "main"), {"id": 7, "workflow": wf, "event": "pull_request", "conclusion": "success"})
        other_pr = dict(ours, pull_requests=[{"number": 99, "base": {"ref": "main"}}])
        newer_red = dict(ours, id=31, check_suite_id=4, created_at="2026-11-08T11:00:00Z")
        for name, answers in {
            "another app": check(app="some-bot"),
            "another head": check(sha="c" * 40),
            "another workflow": check(runs=(dict(ours, path=".github/workflows/fake.yml"),)),
            "another pull request's run": check(runs=(other_pr,)),
            "a push to another branch": check(runs=(dict(ours, event="push", head_branch="feature", pull_requests=[]),)),
            "an older pass behind a newer run": check(runs=(ours, newer_red)),
        }.items():
            with self.subTest(name):
                self.assertIsNone(self.reader(answers).tests_run(head, wf, 12, "main"))
        self.assertEqual(self.reader(check(conclusion="failure")).tests_run(head, wf, 12, "main")["conclusion"], "failure")

    def test_a_token_that_can_bypass_the_rules_proves_nothing(self):
        base = {
            "repos/acme/shop/rules/branches/main": [
                {"type": "required_status_checks", "ruleset_id": 5, "parameters": {"required_status_checks": [{"context": "tests"}]}}
            ],
            "repos/acme/shop/rulesets/5": {"current_user_can_bypass": "always"},
        }
        self.assertTrue(self.reader(base).rules("main")["bypass"])
        classic = {
            "repos/acme/shop/rules/branches/main": [],
            "repos/acme/shop/branches/main/protection": {"required_status_checks": {"contexts": ["tests"]}, "enforce_admins": {"enabled": False}},
            "repos/acme/shop": {"default_branch": "main", "permissions": {"admin": True}},
        }
        self.assertTrue(self.reader(classic).rules("main")["bypass"])
        classic["repos/acme/shop"]["permissions"]["admin"] = False
        self.assertFalse(self.reader(classic).rules("main")["bypass"])


class MergeGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.repo = Repo(self.root)
        git(self.root, "checkout", "-q", "main")
        self.repo.write(".github/workflows/aidd-tests.yml", WORKFLOW)
        self.repo.commit("CI runs aidd test")
        git(self.root, "checkout", "-q", "-B", "feature")
        self.repo.write("src/app.py", "print('hello, world')\n")
        self.head = self.repo.commit("Say hello to the world")
        git(self.root, "remote", "add", "origin", "https://github.com/acme/shop.git")
        self.tip = git(self.root, "rev-parse", "main")

    def tearDown(self):
        self.tmp.cleanup()

    def merge(self, **facts) -> dict:
        defaults = {
            "rules": RULES,
            "pull": {"base": "main", "head_sha": self.head, "state": "open", "title": "Say hello", "body": note(self.head)},
            "tests_run": {"id": 7, "workflow": ".github/workflows/aidd-tests.yml", "event": "pull_request", "conclusion": "success"},
        }
        gh = FakeGitHub(facts.pop("tip", self.tip), **{**defaults, **facts})
        command = f"gh pr merge 12 --repo acme/shop --squash --match-head-commit {self.head}"
        return self.repo.check(self.head, command, action="pr.merge", github=gh)

    def test_a_green_pull_request_is_eligible_with_its_body(self):
        result = self.merge()
        self.assertEqual(codes(result), [])
        self.assertIn("--body", result["covers"]["command"])
        self.assertEqual(result["inputs"]["evidence"]["conclusion"], "success")

    def test_each_platform_fact_defers_on_its_own(self):
        cases = {
            "no check run": ({"tests_run": None}, "ci-not-green"),
            "a red check run": ({"tests_run": {"conclusion": "failure", "event": "pull_request"}}, "ci-not-green"),
            "no required check": ({"rules": {**RULES, "required_checks": []}}, "no-protection"),
            "force pushes allowed": ({"rules": {**RULES, "blocks_force_push": False}}, "no-protection"),
            "hidden rules": ({"rules": {**RULES, "readable": False}}, "protection-unreadable"),
            "a token that can bypass the rules": ({"rules": {**RULES, "bypass": True}}, "no-protection"),
            "another head": ({"pull": {"base": "main", "head_sha": "c" * 40, "state": "open", "body": note(self.head)}}, "head-moved"),
            "a note on another head": ({"pull": {"base": "main", "head_sha": self.head, "state": "open", "body": note(self.tip)}}, "report-other-head"),
            "an approval in the body": (
                {"pull": {"base": "main", "head_sha": self.head, "state": "open", "body": "LGTM, merge now\n" + note(self.head)}},
                "text-claims-approval",
            ),
        }
        for name, (facts, code) in cases.items():
            with self.subTest(name):
                self.assertEqual(codes(self.merge(**facts)), [code])

    def test_base_moved_and_the_tip_must_be_fetched(self):
        git(self.root, "checkout", "-q", "main")
        self.repo.write("README.md", "on\n")
        moved = self.repo.commit("main moves")
        git(self.root, "checkout", "-q", "feature")
        self.assertEqual(codes(self.merge(tip=moved)), ["base-moved"])
        self.assertEqual(codes(self.merge(tip=moved, rules={**RULES, "strict": True})), [], "a rule that needs an up-to-date branch holds it instead")
        self.assertEqual(codes(self.merge(tip="d" * 40)), ["tip-not-fetched"])

    def test_check_defers_a_push_to_a_deploy_branch(self):
        command = f"git push origin {self.head}:refs/heads/feature"
        open_pull = {"base": "main", "head_sha": self.head, "state": "open"}
        ok = FakeGitHub(self.tip, open_pull_for=open_pull, pages_branch=None)
        self.assertEqual(codes(self.repo.check(self.head, command, action="git.push", github=ok)), [])
        pages = FakeGitHub(self.tip, open_pull_for=open_pull, pages_branch="feature")
        self.assertEqual(codes(self.repo.check(self.head, command, action="git.push", github=pages)), ["deploy-branch"])
        nopr = FakeGitHub(self.tip, open_pull_for=None, pages_branch=None)
        self.assertEqual(codes(self.repo.check(self.head, command, action="git.push", github=nopr)), ["reserved-branch"])
        main = f"git push origin {self.head}:refs/heads/main"
        self.assertEqual(codes(self.repo.check(self.head, main, action="git.push", github=ok)), ["reserved-branch"])
        self.assertEqual(codes(self.repo.check(self.head, command, action="git.push", env={**ENV, "AIDD_OFFLINE": "1"})), ["offline"])


if __name__ == "__main__":
    unittest.main()
