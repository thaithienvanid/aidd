"""Approving where a platform's gate decides (a remote and a CI gate: "preflight"): the approval goes on the pull
request as the person, never into this machine's decision records, which that gate never reads; and `aidd land` refuses."""

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
from aidd.gate import placement
from aidd.platforms import github_person
from aidd.workitems import decision_records


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
        # The person published this branch: the platform's gate decides it from here.
        git(root, "update-ref", f"refs/remotes/origin/{git(root, 'branch', '--show-current')}", "HEAD")

    def fake(self, login="alice", head=None) -> FakeGitHub:
        head = head or git(self.root, "rev-parse", "HEAD")
        return FakeGitHub(login, [{"number": 7, "html_url": "https://github.com/acme/shop/pull/7", "head": {"sha": head}}])

    def records(self) -> str:
        return git(self.root, "for-each-ref", decision_records.DECISIONS_REF).strip()

    def test_an_approvers_approval_is_posted_on_the_pull_request_and_nothing_is_recorded_here(self):
        gh = self.fake()
        with mock.patch.object(github_person, "_person_client", return_value=gh):
            shown = json.loads(run(self.root, "approve", "spec", "SPEC-1", "--show")[1])
            self.assertEqual(shown["posts_to"], {"repo": "acme/shop", "number": 7, "url": "https://github.com/acme/shop/pull/7", "as": "alice"})
            code, out = run(self.root, "approve", "spec", "SPEC-1", "--confirmed", shown["commit"])
        self.assertEqual(code, 0, out)
        self.assertIn("posted on https://github.com/acme/shop/pull/7#posted as @alice", out)
        ((path, body),) = gh.posts
        self.assertEqual(path, "/repos/acme/shop/issues/7/comments")
        self.assertEqual(body["body"], f"/aidd approve-spec SPEC-1 {shown['commit']}")
        self.assertEqual(self.records(), "")  # the platform's gate never reads this machine's decision records

    def test_an_account_outside_the_pool_posts_nothing_and_says_how(self):
        gh = self.fake(login="someone-else")
        with mock.patch.object(github_person, "_person_client", return_value=gh):
            shown = json.loads(run(self.root, "approve", "spec", "SPEC-1", "--show")[1])
            self.assertTrue(any("@someone-else, who is not an Approver here" in p for p in shown["problems"]), shown["problems"])
            code, out = run(self.root, "approve", "spec", "SPEC-1", "--confirmed", shown["commit"])
        self.assertEqual(code, 1, out)
        self.assertIn("gh auth login", out)
        self.assertIn("/aidd approve-spec SPEC-1", out)  # the line to post by hand
        self.assertEqual((gh.posts, self.records()), ([], ""))

    def test_the_approver_account_signs_whichever_account_is_active(self):
        """Two accounts signed in to gh, the active one no Approver: aidd uses the Approver's token, read locally."""
        tokens = {"alice": "token-of-alice"}

        def fake_gh(argv):
            return tokens.get(argv[3]) if argv[:3] == ["auth", "token", "--user"] else "token-of-the-active-account"

        with mock.patch.dict(os.environ), mock.patch.object(github_person, "_gh", side_effect=fake_gh):
            os.environ.pop("GH_TOKEN", None)
            os.environ.pop("GITHUB_TOKEN", None)
            self.assertEqual(github_person.approver_login(["@org/leads", "email:a@example.com", "@bob", "@alice"]), "alice")
            self.assertEqual(github_person._person_token("alice"), "token-of-alice")
            self.assertEqual(github_person._person_token(None), "token-of-the-active-account")
            self.assertIsNone(github_person.approver_login(["@bob"]))
            os.environ["GH_TOKEN"] = "set-by-the-person"
            self.assertIsNone(github_person.approver_login(["@alice"]))  # the token they set decides
            self.assertEqual(github_person._person_token("alice"), "set-by-the-person")

    def test_no_pull_request_or_an_unpushed_head_posts_nothing(self):
        for gh, said in ((FakeGitHub("alice", []), "has no open pull request"), (self.fake(head="f" * 40), "push discount, then approve")):
            with self.subTest(said=said), mock.patch.object(github_person, "_person_client", return_value=gh):
                h = json.loads(run(self.root, "approve", "spec", "SPEC-1", "--show")[1])["commit"]
                code, out = run(self.root, "approve", "spec", "SPEC-1", "--confirmed", h)
                self.assertEqual(code, 1, out)
                self.assertIn(said, out)
                self.assertEqual(gh.posts, [])

    def test_a_merge_approval_is_an_approving_review_of_exactly_the_head(self):
        gh = self.fake()
        head = git(self.root, "rev-parse", "HEAD")
        with contextlib.chdir(self.root), contextlib.redirect_stdout(io.StringIO()), mock.patch.object(github_person, "_person_client", return_value=gh):
            self.assertEqual(decide._approve_on_platform("discount", head, ask=False), 0)
        ((path, body),) = gh.posts
        self.assertEqual((path, body["event"], body["commit_id"]), ("/repos/acme/shop/pulls/7/reviews", "APPROVE", head))
        self.assertEqual(self.records(), "")

    def test_a_typed_merge_it_posts_the_review_and_covers_a_later_fix(self):
        """A "merge it" on a platform is the person's review of the head they saw, and a decision on this machine (with
        their login) that a later head of the same work ships under: the gate or the reviewer asks for a fix, and
        nobody asks the person again."""
        from aidd import config
        from aidd.cli.commands import typed_decisions

        gh = self.fake()
        head = git(self.root, "rev-parse", "HEAD")
        with mock.patch.object(github_person, "_person_client", return_value=gh), mock.patch.dict(os.environ, {"GH_TOKEN": "t"}):
            note = typed_decisions.record("merge it", str(self.root))
        self.assertIn("recorded it from their own words", note or "")
        self.assertIn("run `aidd approve merge`", note or "")
        ((path, body),) = gh.posts
        self.assertEqual((path, body["commit_id"]), ("/repos/acme/shop/pulls/7/reviews", head))
        said = git(self.root, "log", "-1", "--format=%B", decision_records.DECISIONS_REF)
        self.assertIn(f"{decision_records.LAND_TRAILER}: {head}", said)
        self.assertIn(f"{decision_records.LOGIN_TRAILER}: alice", said)
        self.assertIn(f"{decision_records.SAID_TRAILER}: merge it", said)
        Path(self.root, "app/discount.py").write_text("def discount(total, pct):\n    return total\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "fix: what the reviewer asked")
        cfg = config.load_file(config.CONFIG_PATH, str(self.root))
        covered = decision_records.land_decision(cfg, str(self.root), git(self.root, "rev-parse", "HEAD"))
        self.assertEqual((covered or {}).get("head"), head)
        self.assertFalse((covered or {}).get("exact"))
        self.assertEqual(decide.land_it_decided_via(covered), f"land-it:{covered['sha'][:12]}")
        self.assertEqual((covered or {}).get("words"), "merge it")
        self.assertTrue(decision_records.covers_platform_merge(covered or {}, "preflight"))

    def test_a_land_it_alone_never_approves_the_merge_on_the_platform(self):
        """ "land it" lands on the local trunk; on a platform only the person's "merge it" is their Merge approval."""
        land_it = {"sha": "f" * 40, "head": "a" * 40, "branch": "discount", "words": "land it", "exact": True}
        self.assertFalse(decision_records.covers_platform_merge(land_it, "preflight"))
        self.assertTrue(decision_records.covers_platform_merge(land_it, "local"))
        self.assertNotIn(decision_records.SAID_TRAILER, decision_records.land_said_line("a" * 40, "discount"))
        self.assertIn(f"{decision_records.SAID_TRAILER}: merge it", decision_records.land_said_line("a" * 40, "discount", words="merge it"))

    def test_ship_refuses_where_the_platform_merges(self):
        code, out = run(self.root, "land")
        self.assertEqual(code, 1, out)
        self.assertIn("merges there once `aidd/gate` passes", out)
        shown = json.loads(run(self.root, "land", "--show")[1])
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

    PR = github_person.PullRequest("acme/shop", 7, "https://github.com/acme/shop/pull/7", "a" * 40, "alice")

    def test_a_ruleset_or_classic_protection_that_requires_the_gate_turns_it_on(self):
        ruleset = [{"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "aidd/gate"}]}}]
        for fake in (AutoMergeGitHub(ruleset), AutoMergeGitHub([], {"required_status_checks": {"contexts": ["aidd/gate"]}})):
            with self.subTest(rules=bool(fake.rules)):
                self.assertIsNone(github_person.enable_auto_merge(self.PR, client=fake))
                ((path, data),) = fake.posts
                self.assertEqual((path, data["variables"]), ("/graphql", {"id": "PR_7"}))

    def test_a_base_branch_that_does_not_require_the_gate_gets_no_auto_merge(self):
        other = [{"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "ci/test"}]}}]
        fake = AutoMergeGitHub(other, {"required_status_checks": {"contexts": ["ci/test"]}})
        why = github_person.enable_auto_merge(self.PR, client=fake)
        self.assertIn("`aidd/gate` is not a required check on main", why or "")
        self.assertEqual(fake.posts, [])


class StandingAutoMergeTests(unittest.TestCase):
    """Under a standing approval on a platform, aidd's approving review turns on auto-merge, so the pull request merges
    once `aidd/gate` passes; `stop approving` turns off exactly the auto-merges that approval turned on."""

    PR = github_person.PullRequest("acme/shop", 7, "https://github.com/acme/shop/pull/7", "a" * 40, "alice")

    def test_the_standing_approval_turns_on_auto_merge_and_says_so_in_its_review(self):
        from aidd.cli.commands import decide as d

        shown = {"problems": [], "failing": [], "pending": []}
        with (
            mock.patch.object(d, "merge_preview", return_value=shown),
            mock.patch.object(placement, "platform_of", return_value="preflight"),
            mock.patch.object(d, "_approve_on_platform", return_value=0) as approved,
        ):
            d._merge_under_standing(mock.Mock(), {"sha": "f" * 40, "since": "2026-10-20T00:25"}, "a" * 40, "discount")
        self.assertEqual(approved.call_args.kwargs, {"ask": False, "auto_merge": True, "decided_via": "standing:ffffffffffff"})
        with (
            mock.patch.object(d, "_platform_target", return_value=(self.PR, None)),
            mock.patch.object(github_person, "approve_pull_request", return_value=self.PR.url) as reviewed,
            mock.patch.object(github_person, "enable_auto_merge", return_value=None) as auto,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            d._approve_on_platform("discount", "a" * 40, ask=False, auto_merge=True, decided_via="standing:ffffffffffff")
        self.assertIn(github_person.STANDING_REVIEW, reviewed.call_args.args[2])
        auto.assert_called_once()

    def test_stop_approving_turns_off_only_what_the_standing_approval_turned_on(self):
        def pr(n, enabled_by, body, author="alice"):
            return {
                "id": f"PR_{n}",
                "url": f"https://github.com/acme/shop/pull/{n}",
                "autoMergeRequest": {"enabledBy": {"login": enabled_by}} if enabled_by else None,
                "reviews": {"nodes": [{"author": {"login": author}, "body": body}]},
            }

        nodes = [
            pr(1, "alice", "Merge approval of aaa, under your standing approval (standing:fff)."),
            pr(2, "alice", 'Merge approval of bbb, under your "merge it" (prompt).'),  # the person's own: it stays on
            pr(3, "bob", "Merge approval of ccc, under your standing approval (standing:fff)."),  # another account turned it on
            pr(4, None, "Merge approval of ddd, under your standing approval (standing:fff)."),  # nothing to turn off
        ]

        class Fake(FakeGitHub):
            def post(self, path, data):
                self.posts.append((path, data))
                if "query(" not in data["query"]:
                    return {"data": {}}
                first = data["variables"]["after"] is None  # two pages: every open pull request is read
                page = {"nodes": nodes[:2] if first else nodes[2:], "pageInfo": {"hasNextPage": first, "endCursor": "c1"}}
                return {"data": {"repository": {"pullRequests": page}}}

        fake = Fake("alice", [])
        with mock.patch.object(github_person, "origin_repo", return_value="acme/shop"):
            off, why = github_person.disable_standing_auto_merges(".", ["@alice"], client=fake)
        self.assertEqual(off, ["https://github.com/acme/shop/pull/1"])
        self.assertIn("pull/3 (auto-merge turned on by @bob)", why or "")  # named, never passed over in silence
        disabled = [d["variables"]["id"] for _, d in fake.posts if "disablePullRequestAutoMerge" in d["query"]]
        self.assertEqual(disabled, ["PR_1"])

    def test_an_answer_github_did_not_give_is_never_a_success(self):
        class Says(FakeGitHub):
            def __init__(self, answer, login="alice"):
                super().__init__(login, [])
                self.answer = answer

            def post(self, path, data):
                return self.answer

        cases = (
            (Says({"errors": [{"message": "rate limited"}], "data": None}), "rate limited"),
            (Says({"data": {"repository": None}}), "GitHub did not return acme/shop"),
            (Says({"data": {}}, login=""), "GitHub did not say who you are"),
        )
        for fake, why in cases:
            with self.subTest(why=why), mock.patch.object(github_person, "origin_repo", return_value="acme/shop"):
                off, said = github_person.disable_standing_auto_merges(".", ["@alice"], client=fake)
                self.assertEqual(off, [])
                self.assertIn(why, said or "")

    def test_the_stop_never_waits_on_github(self):
        from aidd.cli.commands import standing

        with mock.patch.object(placement, "trunk_on_platform", return_value=True):
            with mock.patch.object(github_person, "disable_standing_auto_merges", return_value=([], "offline (AIDD_OFFLINE=1)")):
                self.assertIn("turn them off on the open pull requests", standing._auto_merges_off())
            with mock.patch.object(github_person, "disable_standing_auto_merges", return_value=(["https://github.com/acme/shop/pull/1"], None)):
                self.assertIn("Turned off the auto-merge it turned on: https://github.com/acme/shop/pull/1", standing._auto_merges_off())
        with mock.patch.object(placement, "trunk_on_platform", return_value=False):
            self.assertEqual(standing._auto_merges_off(), "")


if __name__ == "__main__":
    unittest.main()
