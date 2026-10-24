"""`aidd publish` on GitLab: it pushes, opens (or finds) the branch's merge request as the person, and carries their
recorded Spec approvals there as notes, with their own token, never a bot's. The counterpart of the GitHub cases in
test_publish.py and test_platform_approve.py, against a fake GitLab API; not yet run against a real instance."""

import os
import shutil
import unittest
from pathlib import Path
from unittest import mock

from helpers import FakeTransport, RepoTemplateCase, git
from test_flows import as_person, shop, spec_and_tests

from aidd.kernel import http
from aidd.platforms import gitlab, gitlab_person
from aidd.workitems import decision_records

GIT = shutil.which("git") is not None
API = "https://gitlab.com/api/v4"
PROJECT = gitlab_person.GitLabProject("gitlab.com", "acme/shop")


def gitlab_ci(root: Path) -> None:
    Path(root, ".gitlab").mkdir(parents=True, exist_ok=True)
    Path(root, ".gitlab/aidd.gitlab-ci.yml").write_text("aidd-gate: {}\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "ci: the gate")


@unittest.skipUnless(GIT, "git is required")
class GitLabPublishTests(RepoTemplateCase):
    """`aidd publish` where the gate runs on GitLab: the merge request, and the Spec approvals it carries."""

    @classmethod
    def build_template(cls, root):
        shop(root)
        far = root / ".git" / "far.git"
        git(root, "init", "-q", "--bare", str(far))
        git(root, "remote", "add", "origin", str(far))
        git(root, "push", "-q", "origin", "main")
        git(root, "fetch", "-q", "origin")
        spec_and_tests(root)

    def setUp(self):
        super().setUp()
        git(self.root, "remote", "set-url", "origin", str(self.root / ".git" / "far.git"))
        gitlab_ci(self.root)
        self.head = git(self.root, "rev-parse", "HEAD")
        self.mr = gitlab_person.MergeRequest(PROJECT, 7, "https://gitlab.com/acme/shop/-/merge_requests/7", self.head, "me")

    def publish(self, *argv: str, target=None, why=None):
        with (
            mock.patch.object(gitlab_person, "gitlab_project", return_value=PROJECT),  # origin here is a local path
            mock.patch.object(gitlab_person, "open_merge_request", return_value=(self.mr.url, None)) as opened,
            mock.patch.object(gitlab_person, "gitlab_approval_target", return_value=(None, why) if why else (target or self.mr, None)) as aimed,
            mock.patch.object(gitlab_person, "post_gitlab_spec_approval", return_value=self.mr.url) as posted,
        ):
            code, out, err = as_person(self.root, "publish", *argv)
        self.aimed = aimed
        return code, out + err, opened, posted

    def test_where_gitlab_runs_the_gate_it_opens_the_merge_request_and_carries_the_spec_approval(self):
        decision_records.record_local_approval(decision_records.approve_spec_line("SPEC-1", self.head), str(self.root))
        code, out, opened, posted = self.publish()
        self.assertEqual(code, 0, out)
        self.assertEqual(opened.call_args.args[1:3], ("discount", "main"))
        self.assertEqual(posted.call_args.args[1], f"/aidd approve-spec SPEC-1 {self.head}")
        self.assertIn("merge request: https://gitlab.com/acme/shop/-/merge_requests/7", out)
        self.assertIn("carried your Spec approval of SPEC-1", out)
        self.assertIn("Approve the merge request on GitLab", out)  # Merge approval stays the person's MR approval
        self.assertEqual(self.aimed.call_args.kwargs["head"], self.head)  # the line goes only where the pushed head is

    def test_a_merge_request_that_names_another_head_gets_no_spec_approval_and_says_why(self):
        decision_records.record_local_approval(decision_records.approve_spec_line("SPEC-1", self.head), str(self.root))
        code, out, _, posted = self.publish(why="the merge request names head aaaaaaaaaaaa, not the one you just pushed")
        self.assertEqual(code, 0, out)
        posted.assert_not_called()
        self.assertIn("aidd carried no Spec approval to the merge request: the merge request names head aaaaaaaaaaaa", out)

    def test_another_persons_spec_approval_is_never_carried(self):
        env = {"GIT_AUTHOR_EMAIL": "someone@example.com", "GIT_COMMITTER_EMAIL": "someone@example.com"}
        with mock.patch.dict("os.environ", env):
            decision_records.record_local_approval(decision_records.approve_spec_line("SPEC-1", self.head), str(self.root))
        code, out, _, posted = self.publish()
        self.assertEqual(code, 0, out)
        posted.assert_not_called()

    def test_a_remote_other_than_origin_gets_no_merge_request_from_aidd(self):
        other = self.root / ".git" / "other.git"
        git(self.root, "init", "-q", "--bare", str(other))
        git(self.root, "remote", "add", "other", str(other))
        code, out, opened, _ = self.publish("--remote", "other")
        self.assertEqual(code, 0, out)
        opened.assert_not_called()
        self.assertIn("no pull request opened", out)


def fake_gitlab(user: dict, mrs: list[dict], created: dict | None = None, api: str = API) -> FakeTransport:
    return FakeTransport(
        {
            f"{api}/user": ({}, user),
            f"{api}/projects/acme%2Fshop/merge_requests/7/notes": ({}, {"id": 1}),
            f"{api}/projects/acme%2Fshop/merge_requests?": ({}, mrs),
            f"{api}/projects/acme%2Fshop/merge_requests": ({}, created or {}),
            f"{api}/projects/acme%2Fshop": ({}, {"id": 7, "path_with_namespace": "acme/shop"}),
        }
    )


def client(t: FakeTransport) -> gitlab.Client:
    return gitlab.Client("person-token", API, transport=t)


MR = {"iid": 7, "web_url": "https://gitlab.com/acme/shop/-/merge_requests/7", "sha": "a" * 40, "source_project_id": 7, "target_project_id": 7}
ALICE = {"username": "alice", "bot": False}


@unittest.skipUnless(GIT, "git is required")
class GitLabPersonTests(RepoTemplateCase):
    """The person's side of GitLab: who the token is, the merge request a line goes on, and the note it posts."""

    @classmethod
    def build_template(cls, root):
        shop(root)
        git(root, "remote", "add", "origin", "git@gitlab.com:acme/shop.git")

    def test_an_approvers_line_is_posted_as_a_note_on_the_merge_request(self):
        t = fake_gitlab(ALICE, [MR])
        mr, why = gitlab_person.gitlab_approval_target(str(self.root), "discount", ["@alice"], head="a" * 40, client=client(t))
        self.assertIsNone(why)
        self.assertEqual((mr.iid, mr.username, mr.head_sha, mr.project), (7, "alice", "a" * 40, PROJECT))
        gitlab_person.post_gitlab_spec_approval(mr, "/aidd approve-spec SPEC-1 " + "b" * 40, client=client(t))
        (method, url, auth, data) = t.calls[-1]
        self.assertEqual((method, url, data), ("POST", f"{API}/projects/acme%2Fshop/merge_requests/7/notes", {"body": "/aidd approve-spec SPEC-1 " + "b" * 40}))
        self.assertEqual(auth, ("PRIVATE-TOKEN", "person-token"))  # the person's own token
        self.assertIn(("GET", f"{API}/projects/acme%2Fshop/merge_requests?source_branch=discount&state=opened"), [c[:2] for c in t.calls])

    def test_an_account_outside_the_pool_posts_nothing_and_says_how(self):
        t = fake_gitlab({"username": "someone-else", "bot": False}, [MR])
        mr, why = gitlab_person.gitlab_approval_target(str(self.root), "discount", ["@alice"], head="a" * 40, client=client(t))
        self.assertIsNone(mr)
        self.assertIn("@someone-else, who is not an Approver here", why)
        self.assertIn("glab auth login", why)

    def test_a_bot_token_posts_nothing(self):
        # A project or group access token signs in as a bot: an approval line from it is never the person's decision.
        # GitLab answers `bot` on GET /user; an answer without it is no person either (fail closed).
        users = (
            {"username": "project_7_bot_4ffca233d8298ea1", "bot": True},
            {"username": "group_42_bot_ab12", "bot": False},
            {"username": "alice", "bot": True},
            {"username": "alice"},
        )
        for user in users:
            with self.subTest(user=user):
                t = fake_gitlab(user, [MR])
                mr, why = gitlab_person.gitlab_approval_target(str(self.root), "discount", ["@alice", f"@{user['username']}"], head="a" * 40, client=client(t))
                self.assertIsNone(mr)
                self.assertIn("a bot account, so aidd posts nothing", why)
                url, why = gitlab_person.open_merge_request(str(self.root), "discount", "main", client=client(t))
                self.assertIsNone(url)
                self.assertEqual([c for c in t.calls if c[0] == "POST"], [])

    def test_no_merge_request_posts_nothing(self):
        mr, why = gitlab_person.gitlab_approval_target(str(self.root), "discount", ["@alice"], head="a" * 40, client=client(fake_gitlab(ALICE, [])))
        self.assertIsNone(mr)
        self.assertIn("has no open merge request", why)

    def test_publish_opens_the_merge_request_or_names_the_open_one(self):
        t = fake_gitlab(ALICE, [MR])
        self.assertEqual(gitlab_person.open_merge_request(str(self.root), "discount", "main", client=client(t)), (MR["web_url"], None))
        self.assertEqual([c for c in t.calls if c[0] == "POST"], [])
        t = fake_gitlab(ALICE, [], created={"web_url": "https://gitlab.com/acme/shop/-/merge_requests/8"})
        url, why = gitlab_person.open_merge_request(str(self.root), "discount", "main", client=client(t))
        self.assertEqual((url, why), ("https://gitlab.com/acme/shop/-/merge_requests/8", None))
        ((method, path, _, data),) = [c for c in t.calls if c[0] == "POST"]
        self.assertEqual(path, f"{API}/projects/acme%2Fshop/merge_requests")
        self.assertEqual((data["source_branch"], data["target_branch"]), ("discount", "main"))

    def test_origin_names_the_project_and_github_is_never_gitlab(self):
        for url, want in (
            ("https://gitlab.com/acme/shop.git", ("gitlab.com", "acme/shop", "https://gitlab.com/api/v4")),
            ("git@gitlab.example.com:acme/sub/shop.git", ("gitlab.example.com", "acme/sub/shop", "https://gitlab.example.com/api/v4")),
            # An ssh port is the git server's, never the API's; an https port is the API's too.
            ("ssh://git@gitlab.example.com:2222/acme/shop", ("gitlab.example.com", "acme/shop", "https://gitlab.example.com/api/v4")),
            ("https://gitlab.example.com:8443/acme/shop.git", ("gitlab.example.com:8443", "acme/shop", "https://gitlab.example.com:8443/api/v4")),
            ("https://gitlab.example.com:443/acme/shop.git", ("gitlab.example.com", "acme/shop", "https://gitlab.example.com/api/v4")),
            ("https://github.com/acme/shop.git", None),
            ("/tmp/far.git", None),
        ):
            with self.subTest(url=url):
                git(self.root, "remote", "set-url", "origin", url)
                found = gitlab_person.gitlab_project(str(self.root))
                self.assertEqual((found.netloc, found.path, found.api) if found else None, want)

    def test_a_forks_merge_request_from_a_branch_of_the_same_name_is_never_the_persons(self):
        # GitLab lists every merge request into acme/shop from a branch named `discount`, a fork's included. Mallory
        # opened one from her fork (project 999) first: publish never names it, nor posts the person's line on it.
        fork_mr = MR | {"iid": 66, "web_url": "https://gitlab.com/acme/shop/-/merge_requests/66", "sha": "f" * 40, "source_project_id": 999}
        t = fake_gitlab(ALICE, [fork_mr], created={"web_url": "https://gitlab.com/acme/shop/-/merge_requests/8"})
        self.assertEqual(
            gitlab_person.open_merge_request(str(self.root), "discount", "main", client=client(t)), ("https://gitlab.com/acme/shop/-/merge_requests/8", None)
        )
        mr, why = gitlab_person.gitlab_approval_target(str(self.root), "discount", ["@alice"], head="f" * 40, client=client(t))
        self.assertIsNone(mr)
        self.assertIn("has no open merge request", why)
        self.assertNotIn("merge_requests/66", " ".join(c[1] for c in t.calls))
        # A project GitLab does not name by id: nothing is taken as the person's.
        t = fake_gitlab(ALICE, [MR])
        t.routes[f"{API}/projects/acme%2Fshop"] = ({}, {})
        self.assertEqual(gitlab_person.open_merge_request(str(self.root), "discount", "main", client=client(t))[0], None)

    def test_a_merge_request_that_names_another_head_gets_no_line(self):
        # The line binds the pushed head: a merge request GitLab has not yet moved to it, or one that holds other work,
        # gets nothing, and the reason names the step that works.
        t = fake_gitlab(ALICE, [MR])
        mr, why = gitlab_person.gitlab_approval_target(str(self.root), "discount", ["@alice"], head="b" * 40, client=client(t))
        self.assertIsNone(mr)
        self.assertIn(f"names head {'a' * 12}, not {'b' * 12} that you just pushed", why)
        self.assertIn("type `publish` again", why)
        self.assertEqual([c for c in t.calls if c[0] == "POST"], [])

    def test_a_token_goes_only_to_the_host_it_was_given_for(self):
        def fake_glab(argv):
            return "glab-token-for-" + argv[-1] if argv[:3] == ["config", "get", "token"] else None

        with mock.patch.dict(os.environ, {"GITLAB_TOKEN": "env-token"}), mock.patch.object(gitlab_person, "_glab", side_effect=fake_glab):
            for name in ("GITLAB_HOST", "GL_HOST", "GITLAB_ACCESS_TOKEN", "OAUTH_TOKEN"):
                os.environ.pop(name, None)
            self.assertEqual(gitlab_person._person_token("gitlab.com"), "env-token")  # GITLAB_TOKEN is gitlab.com's by default
            # origin is local git config an agent can change: GITLAB_TOKEN never goes to a host GITLAB_HOST does not name.
            self.assertEqual(gitlab_person._person_token("evil.example"), "glab-token-for-evil.example")
            os.environ["GITLAB_HOST"] = "https://gitlab.example.com"
            self.assertEqual(gitlab_person._person_token("gitlab.example.com"), "env-token")
            self.assertEqual(gitlab_person._person_token("gitlab.com"), "glab-token-for-gitlab.com")
        with mock.patch.dict(os.environ, {"AIDD_OFFLINE": "1"}):
            self.assertIn("offline", gitlab_person._person_client(PROJECT))

    @unittest.skipIf(os.name == "nt", "the glab stand-in is a shell script")
    def test_glab_never_hands_back_the_environments_token_for_another_host(self):
        # glab reads GITLAB_TOKEN (and its other names) ahead of its stored config, for every host. So asked for
        # origin's host, glab would answer with the token given for gitlab.com, and aidd would send it there.
        stand_in = self.root / ".git" / "fakebin"
        stand_in.mkdir()
        glab = stand_in / "glab"
        glab.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = config ] && [ "$2" = get ] && [ "$3" = token ]; then\n'
            '  for v in "$GITLAB_TOKEN" "$GITLAB_ACCESS_TOKEN" "$OAUTH_TOKEN" "$GITLAB_HOST" "$GITLAB_URI" "$GL_HOST" "$CI_JOB_TOKEN"; do\n'
            '    if [ -n "$v" ]; then printf "%s\\n" "$v"; exit 0; fi\n'
            "  done\n"
            '  printf "stored-token-for-%s\\n" "$5"; exit 0\n'
            "fi\n"
            "exit 1\n",
            encoding="utf-8",
        )
        glab.chmod(0o755)
        git(self.root, "remote", "set-url", "origin", "https://evil.example:8443/acme/shop.git")
        env = {
            "PATH": f"{stand_in}{os.pathsep}{os.environ['PATH']}",
            "GITLAB_TOKEN": "glpat-for-gitlab-com",
            "GITLAB_ACCESS_TOKEN": "glpat-other",
            "OAUTH_TOKEN": "oauth",
            "GITLAB_URI": "gitlab.com",
            "CI_JOB_TOKEN": "job",
        }
        with mock.patch.dict(os.environ, env):
            for name in ("GITLAB_HOST", "GL_HOST", "AIDD_OFFLINE"):
                os.environ.pop(name, None)
            project = gitlab_person.gitlab_project(str(self.root))
            self.assertEqual(gitlab_person._person_token(project.netloc), "stored-token-for-evil.example:8443")
            t = fake_gitlab(ALICE, [], api="https://evil.example:8443/api/v4")
            with mock.patch.object(http, "request", t):
                gitlab_person.open_merge_request(str(self.root), "discount", "main")
        self.assertTrue(t.calls)
        for _, url, auth, _ in t.calls:
            self.assertTrue(url.startswith("https://evil.example:8443/api/v4/"), url)
            self.assertEqual(auth, ("PRIVATE-TOKEN", "stored-token-for-evil.example:8443"))


if __name__ == "__main__":
    unittest.main()
