"""Approving where a platform's gate decides (a remote and a CI gate: "preflight"): the approval goes on the pull
request as the person, never into this machine's ledger, which that gate never reads; and `aidd ship` refuses."""

import contextlib
import io
import json
import os
import shutil
import unittest
from pathlib import Path
from unittest import mock

from helpers import RepoTemplateCase, git
from test_flows import shop, spec_and_tests

from aidd.cli import app
from aidd.cli.commands import decide
from aidd.platforms import github
from aidd.workitems import approval_ledger


class FakeGitHub:
    """The GitHub API as the person's token sees it: who they are, the branch's open pull requests, and what they post."""

    def __init__(self, login: str, pulls: list[dict]):
        self.login, self.pulls, self.posts = login, pulls, []

    def get(self, path: str, params: dict | None = None):
        return {"login": self.login} if path == "/user" else self.pulls

    def post(self, path: str, data: dict):
        self.posts.append((path, data))
        return {"html_url": "https://github.com/acme/shop/pull/7#posted"}


def run(root, *argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.chdir(root), contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = app.main(list(argv))
    return code, out.getvalue()


@unittest.skipUnless(shutil.which("git"), "git is required")
class PlatformApprovalTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        shop(root, "team", "@alice")
        Path(root, ".github/workflows").mkdir(parents=True)
        Path(root, ".github/workflows/aidd-gate.yml").write_text("name: aidd-gate\n", encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-qm", "ci: the gate")
        git(root, "remote", "add", "origin", "https://github.com/acme/shop.git")
        spec_and_tests(root)

    def fake(self, login="alice", head=None) -> FakeGitHub:
        head = head or git(self.root, "rev-parse", "HEAD")
        return FakeGitHub(login, [{"number": 7, "html_url": "https://github.com/acme/shop/pull/7", "head": {"sha": head}}])

    def ledger(self) -> str:
        return git(self.root, "for-each-ref", approval_ledger.APPROVALS_REF).strip()

    def test_an_approvers_approval_is_posted_on_the_pull_request_and_nothing_is_recorded_here(self):
        gh = self.fake()
        with mock.patch.object(github, "_person_client", return_value=gh):
            shown = json.loads(run(self.root, "approve", "spec", "SPEC-1", "--show")[1])
            self.assertEqual(shown["posts_to"], {"repo": "acme/shop", "number": 7, "url": "https://github.com/acme/shop/pull/7", "as": "alice"})
            code, out = run(self.root, "approve", "spec", "SPEC-1", "--confirmed", shown["hash"])
        self.assertEqual(code, 0, out)
        self.assertIn("posted on https://github.com/acme/shop/pull/7#posted as @alice", out)
        ((path, body),) = gh.posts
        self.assertEqual(path, "/repos/acme/shop/issues/7/comments")
        self.assertEqual(body["body"], f"/aidd approve-spec SPEC-1 {shown['hash']} {shown['commit']}")
        self.assertEqual(self.ledger(), "")  # the platform's gate never reads this machine's ledger

    def test_an_account_outside_the_pool_posts_nothing_and_says_how(self):
        gh = self.fake(login="someone-else")
        with mock.patch.object(github, "_person_client", return_value=gh):
            shown = json.loads(run(self.root, "approve", "spec", "SPEC-1", "--show")[1])
            self.assertTrue(any("@someone-else, who is not an Approver here" in p for p in shown["problems"]), shown["problems"])
            code, out = run(self.root, "approve", "spec", "SPEC-1", "--confirmed", shown["hash"])
        self.assertEqual(code, 1, out)
        self.assertIn("gh auth login", out)
        self.assertIn("/aidd approve-spec SPEC-1", out)  # the line to post by hand
        self.assertEqual((gh.posts, self.ledger()), ([], ""))

    def test_the_approver_account_signs_whichever_account_is_active(self):
        """Two accounts signed in to gh, the active one no Approver: aidd uses the Approver's token, read locally."""
        tokens = {"alice": "token-of-alice"}

        def fake_gh(argv):
            return tokens.get(argv[3]) if argv[:3] == ["auth", "token", "--user"] else "token-of-the-active-account"

        with mock.patch.dict(os.environ), mock.patch.object(github, "_gh", side_effect=fake_gh):
            os.environ.pop("GH_TOKEN", None)
            os.environ.pop("GITHUB_TOKEN", None)
            self.assertEqual(github.approver_login(["@org/leads", "email:a@example.com", "@bob", "@alice"]), "alice")
            self.assertEqual(github._person_token("alice"), "token-of-alice")
            self.assertEqual(github._person_token(None), "token-of-the-active-account")
            self.assertIsNone(github.approver_login(["@bob"]))
            os.environ["GH_TOKEN"] = "set-by-the-person"
            self.assertIsNone(github.approver_login(["@alice"]))  # the token they set decides
            self.assertEqual(github._person_token("alice"), "set-by-the-person")

    def test_no_pull_request_or_an_unpushed_head_posts_nothing(self):
        for gh, said in ((FakeGitHub("alice", []), "has no open pull request"), (self.fake(head="f" * 40), "push discount, then approve")):
            with self.subTest(said=said), mock.patch.object(github, "_person_client", return_value=gh):
                h = json.loads(run(self.root, "approve", "spec", "SPEC-1", "--show")[1])["hash"]
                code, out = run(self.root, "approve", "spec", "SPEC-1", "--confirmed", h)
                self.assertEqual(code, 1, out)
                self.assertIn(said, out)
                self.assertEqual(gh.posts, [])

    def test_a_merge_approval_is_an_approving_review_of_exactly_the_head(self):
        gh = self.fake()
        head = git(self.root, "rev-parse", "HEAD")
        with contextlib.chdir(self.root), contextlib.redirect_stdout(io.StringIO()), mock.patch.object(github, "_person_client", return_value=gh):
            self.assertEqual(decide._approve_on_platform("discount", head, ask=False), 0)
        ((path, body),) = gh.posts
        self.assertEqual((path, body["event"], body["commit_id"]), ("/repos/acme/shop/pulls/7/reviews", "APPROVE", head))
        self.assertEqual(self.ledger(), "")

    def test_a_typed_ship_it_posts_the_review_and_covers_a_later_fix(self):
        """A "ship it" on a platform is the person's review of the head they saw, and a decision on this machine (with
        their login) that a later head of the same work ships under: the gate or the reviewer asks for a fix, and
        nobody asks the person again."""
        from aidd import config
        from aidd.cli.commands import typed_decisions

        gh = self.fake()
        head = git(self.root, "rev-parse", "HEAD")
        with mock.patch.object(github, "_person_client", return_value=gh), mock.patch.dict(os.environ, {"GH_TOKEN": "t"}):
            note = typed_decisions.record("ship it", str(self.root))
        self.assertIn("recorded it from their own words", note or "")
        self.assertIn("run `aidd approve merge`", note or "")
        ((path, body),) = gh.posts
        self.assertEqual((path, body["commit_id"]), ("/repos/acme/shop/pulls/7/reviews", head))
        said = git(self.root, "log", "-1", "--format=%B", approval_ledger.APPROVALS_REF)
        self.assertIn(f"{approval_ledger.SHIP_TRAILER}: {head}", said)
        self.assertIn(f"{approval_ledger.LOGIN_TRAILER}: alice", said)
        Path(self.root, "app/discount.py").write_text("def discount(total, pct):\n    return total\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "fix: what the reviewer asked")
        cfg = config.load_file(config.CONFIG_PATH, str(self.root))
        covered = approval_ledger.ship_decision(cfg, str(self.root), git(self.root, "rev-parse", "HEAD"))
        self.assertEqual((covered or {}).get("head"), head)
        self.assertFalse((covered or {}).get("exact"))
        self.assertEqual(decide.ship_it_confirmed_in(covered), f"ship-it:{covered['sha'][:12]}")

    def test_ship_refuses_where_the_platform_merges(self):
        code, out = run(self.root, "ship")
        self.assertEqual(code, 1, out)
        self.assertIn("merges there once `aidd/gate` passes", out)
        shown = json.loads(run(self.root, "ship", "--show")[1])
        self.assertIn("merges there", shown["problems"][0])


class AutoMergeGitHub(FakeGitHub):
    """The pull request, its base branch's rules (a ruleset) and classic protection, and the GraphQL answer."""

    def __init__(self, rules: list[dict], protection: dict | None = None):
        super().__init__("alice", [])
        self.rules, self.protection = rules, protection or {}

    def get(self, path: str, params: dict | None = None):
        if path == "/repos/acme/shop/pulls/7":
            return {"node_id": "PR_7", "base": {"ref": "main"}}
        if path == "/repos/acme/shop/rules/branches/main":
            return self.rules
        if path == "/repos/acme/shop/branches/main":
            return {"protection": self.protection}
        raise AssertionError(path)

    def post(self, path: str, data: dict):
        self.posts.append((path, data))
        return {"data": {}}


class AutoMergeTests(unittest.TestCase):
    """Auto-merge goes on only where the base branch requires `aidd/gate`: elsewhere GitHub could merge a head the
    gate fails, once the person's approval satisfied the review count."""

    PR = github.PullRequest("acme/shop", 7, "https://github.com/acme/shop/pull/7", "a" * 40, "alice")

    def test_a_ruleset_or_classic_protection_that_requires_the_gate_turns_it_on(self):
        ruleset = [{"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "aidd/gate"}]}}]
        for fake in (AutoMergeGitHub(ruleset), AutoMergeGitHub([], {"required_status_checks": {"contexts": ["aidd/gate"]}})):
            with self.subTest(rules=bool(fake.rules)):
                self.assertIsNone(github.enable_auto_merge(self.PR, client=fake))
                ((path, data),) = fake.posts
                self.assertEqual((path, data["variables"]), ("/graphql", {"id": "PR_7"}))

    def test_a_base_branch_that_does_not_require_the_gate_gets_no_auto_merge(self):
        other = [{"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "ci/test"}]}}]
        fake = AutoMergeGitHub(other, {"required_status_checks": {"contexts": ["ci/test"]}})
        why = github.enable_auto_merge(self.PR, client=fake)
        self.assertIn("`aidd/gate` is not a required check on main", why or "")
        self.assertEqual(fake.posts, [])


if __name__ == "__main__":
    unittest.main()
