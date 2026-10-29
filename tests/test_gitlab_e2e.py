"""The GitLab adapter end to end: a real git repository with a merge request ref, and a fake GitLab API."""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
from helpers import ROOT, FakeTransport, git  # noqa: F401  (ROOT puts src on sys.path)

from aidd.platforms import gitlab
from aidd.kernel import http

API = "https://gitlab.test/api/v4"
CONFIG = """aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@lead"]

tests:
  - name: unit
    command: ["{py}", -c, print('ok')]
"""
BODY = """Fix a typo.

```yaml aidd
route: minor
type: docs
confidence: high
scope: [docs/guide.md]
rollback: Revert the MR.
assisted_by: []

risk:
  summary: Fixes a typo.
  dimensions: []
  reversible: true
```
"""


@unittest.skipUnless(shutil.which("git"), "git is required")
class GitLabEndToEndTests(unittest.TestCase):
    def setUp(self):
        helpers.enforce_by_default(self)  # these test enforce exit codes and the mode's precedence
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.origin, self.work = t / "origin.git", t / "work"
        git(t, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(t, "init", "-q", "-b", "main", str(self.work))
        for k, v in (("user.email", "alice@example.com"), ("user.name", "Alice"), ("commit.gpgsign", "false")):
            git(self.work, "config", k, v)
        (self.work / ".aidd").mkdir()
        self.py = sys.executable.replace("\\", "/")
        (self.work / ".aidd/config.yaml").write_text(CONFIG.format(py=self.py), encoding="utf-8")
        (self.work / "docs").mkdir()
        (self.work / "docs/guide.md").write_text("Teh guide.\n", encoding="utf-8")
        git(self.work, "add", ".")
        git(self.work, "commit", "-qm", "base")
        git(self.work, "remote", "add", "origin", str(self.origin))
        git(self.work, "push", "-q", "origin", "main")
        git(self.work, "checkout", "-qb", "fix")
        (self.work / "docs/guide.md").write_text("The guide.\n", encoding="utf-8")
        git(self.work, "commit", "-qam", "Fix typo")
        self.head = git(self.work, "rev-parse", "HEAD")
        git(self.work, "push", "-q", "origin", f"{self.head}:refs/merge-requests/1/head")
        self.base = git(self.work, "rev-parse", "main")
        self.evidence = t / "evidence.json"
        self.evidence.write_text(
            json.dumps(
                {
                    "aidd_version": "1.0.0",
                    "head_sha": self.head,
                    "base_sha": self.base,
                    "results": [
                        {
                            "name": "unit",
                            "source": "config",
                            "command": [self.py, "-c", "print('ok')"],
                            "red_green": "green",
                            "exit": 0,
                            "status": "passed",
                            "duration_seconds": 0.1,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def transport(self, approver="lead", approved_at="2026-09-25T10:05:00Z", committers_blocked=True, notes=(), settings=None):
        return FakeTransport(
            {
                f"{API}/projects/7/merge_requests/1/commits": (
                    {},
                    [{"id": self.head, "author_email": "alice@example.com", "committer_email": "alice@example.com", "message": "Fix typo"}],
                ),
                f"{API}/projects/7/merge_requests/1/notes": (
                    {},
                    [{"system": True, "body": "approved this merge request", "author": {"id": 7001, "username": approver}, "created_at": approved_at}, *notes],
                ),
                f"{API}/users/": ({}, {"bot": False}),  # GET /users/:id: each approver is a person
                f"{API}/projects/7/merge_requests/1": (
                    {},
                    {"sha": self.head, "target_branch": "main", "description": BODY, "author": {"username": "alice"}, "created_at": "2026-09-25T09:00:00Z"},
                ),
                f"{API}/projects/7/approvals": (
                    {},
                    {"merge_requests_disable_committers_approval": committers_blocked, "merge_requests_author_approval": False, **(settings or {})},
                ),
                f"{API}/projects/7/statuses/": ({}, {}),
            }
        )

    def run_gate(self, transport, **env):
        base_env = {
            "CI_MERGE_REQUEST_IID": "1",
            "CI_PROJECT_ID": "7",
            "CI_API_V4_URL": API,
            "AIDD_GITLAB_TOKEN": "t",
            "CI_PIPELINE_CREATED_AT": "2026-09-25T10:00:00Z",
            "CI_COMMIT_SHA": self.head,
            "CI_PROJECT_PATH": "acme/app",
            "AIDD_MODE": "",
            "AIDD_ORG_PRESET": "",
        }
        record = Path(self.tmp.name) / "record.json"
        self.printed = io.StringIO()
        with mock.patch.dict(os.environ, {**base_env, **env}), mock.patch.object(http, "request", transport), contextlib.redirect_stdout(self.printed):
            code = gitlab.gitlab_gate(cwd=str(self.work), evidence_path=str(self.evidence), record_out=str(record), post=True)
        return code, json.loads(record.read_text(encoding="utf-8")) if record.exists() else None

    def test_an_approved_minor_change_passes(self):
        t = self.transport()
        code, record = self.run_gate(t)
        self.assertEqual((code, record["decision"]), (0, "pass"), record)
        posted = [c for c in t.calls if c[0] == "POST"]
        self.assertIn("state=success", posted[0][1])

    def test_an_approval_before_the_pipeline_does_not_bind(self):
        code, record = self.run_gate(self.transport(approved_at="2026-09-25T09:30:00Z"))
        self.assertEqual((code, record["decision"]), (1, "pending"))

    def test_the_author_cannot_approve(self):
        _, record = self.run_gate(self.transport(approver="alice"))
        self.assertEqual(record["decision"], "pending")

    def test_unlinked_emails_only_warn_under_team(self):
        _, record = self.run_gate(self.transport(committers_blocked=False))
        self.assertEqual(record["decision"], "pass")

    def test_fork_pipelines_fail_closed(self):
        self.assertEqual(self.run_gate(self.transport(), CI_MERGE_REQUEST_PROJECT_ID="8"), (1, None))

    def test_a_pipeline_variable_cannot_make_the_gate_advisory(self):
        # Anyone who may run a pipeline can set AIDD_MODE; only the base branch's config can relax the gate.
        t = self.transport(approver="alice")
        code, record = self.run_gate(t, AIDD_MODE="advisory")
        self.assertEqual((code, record["decision"]), (1, "pending"))
        posted = [c for c in t.calls if c[0] == "POST"]
        self.assertNotIn("advisory", posted[0][1])

    def test_a_stale_pipeline_does_not_decide(self):
        self.assertEqual(self.run_gate(self.transport(), CI_COMMIT_SHA="f" * 40), (1, None))

    def test_retargeting_the_merge_request_voids_an_earlier_approval(self):
        # GitLab records a new target branch as a system note; an approval (10:05) before it (10:10) approved another diff.
        for body in ("changed target branch from `develop` to `main`", "changed automatically target branch to `main` because `develop` was merged"):
            with self.subTest(body=body):
                note = {"system": True, "body": body, "author": {"username": "bob"}, "created_at": "2026-09-25T10:10:00Z"}
                code, record = self.run_gate(self.transport(notes=[note]))
                self.assertEqual((code, record["decision"]), (1, "pending"))
                self.assertEqual(record["approved_by"], [])

    def test_an_approval_after_the_retarget_counts(self):
        note = {"system": True, "body": "changed target branch from `develop` to `main`", "author": {"username": "bob"}, "created_at": "2026-09-25T10:01:00Z"}
        code, record = self.run_gate(self.transport(notes=[note]))
        self.assertEqual((code, record["decision"]), (0, "pass"), record)

    def test_a_merge_train_pipeline_with_no_train_commit_fails_closed(self):
        # A train pipeline is judged on its car's commit (test_gitlab_merge_train.py); one that names none decides nothing.
        t = self.transport()
        self.assertEqual(self.run_gate(t, CI_MERGE_REQUEST_EVENT_TYPE="merge_train", CI_COMMIT_SHA=""), (1, None))
        self.assertIn("merge train", self.printed.getvalue())
        self.assertEqual([c for c in t.calls if c[0] == "POST"], [])

    def test_only_members_gitlab_says_are_people_are_in_a_groups_pool(self):
        # GitLab's members API says nothing of bots, and a group service account has no telltale username, so only
        # GET /users/:id with `bot: false` makes a member a person. A bot, a failed lookup, or no answer leaves it out.
        members = [
            {"id": 1, "username": "lead"},
            {"id": 2, "username": "group_42_bot_4ffca233d8298ea1"},  # a group access token's bot
            {"id": 3, "username": "project_7_bot_ab12"},  # a project access token's bot
            {"id": 4, "username": "release-automation"},  # a group service account
            {"id": 5, "username": "duo-developer-acme"},  # one of GitLab's own bots
            {"id": 6, "username": "quiet"},  # GitLab answers without the field
            {"id": 7, "username": "lost"},  # the lookup fails
            {"username": "no-id"},
        ]
        t = FakeTransport(
            {
                f"{API}/groups/acme%2Fleads/members/all": ({}, members),
                f"{API}/users/1": ({}, {"id": 1, "bot": False}),
                f"{API}/users/2": ({}, {"id": 2, "bot": True}),
                f"{API}/users/3": ({}, {"id": 3, "bot": False}),
                f"{API}/users/4": ({}, {"id": 4, "bot": True}),
                f"{API}/users/5": ({}, {"id": 5, "bot": True}),
                f"{API}/users/6": ({}, {"id": 6}),
            }
        )
        found, shrunk = gitlab._group_members(gitlab.Client("t", API, transport=t), ["acme/leads"])
        self.assertEqual((found, shrunk), ({"acme/leads": ["lead"]}, ["acme/leads"]))
        # An access token's bot is known by its name, without a lookup.
        self.assertNotIn(("GET", f"{API}/users/2"), [c[:2] for c in t.calls])

    def test_a_bots_approval_or_approval_line_never_counts(self):
        # An Approver's username, but GET /users/:id says the account is a bot: its approval and its approval line are
        # recorded as `lead[bot]`, as GitHub names a bot, so neither counts.
        line = {"system": False, "body": "/aidd approve " + self.head, "author": {"id": 9001, "username": "lead"}, "created_at": "2026-09-25T10:06:00Z"}
        t = self.transport(notes=[line])
        t.routes = {f"{API}/users/7001": ({}, {"bot": True}), f"{API}/users/9001": ({}, {"bot": True}), **t.routes}
        code, record = self.run_gate(t)
        self.assertEqual((code, record["decision"]), (1, "pending"), record)
        self.assertIn("merge_approval.agent_approval", [f["code"] for f in record["findings"]])
        self.assertEqual(record["approved_by"], [])
        # The same notes from a person count.
        t = self.transport(notes=[line])
        code, record = self.run_gate(t)
        self.assertEqual((code, record["decision"]), (0, "pass"), record)

    def test_an_approver_gitlab_cannot_vouch_for_never_counts(self):
        # A lookup that fails, or an answer without `bot`: aidd cannot tell a person from a bot, so the approval waits.
        for answer in (None, {"id": 7001, "username": "lead"}):
            with self.subTest(answer=answer):
                routes = {k: v for k, v in self.transport().routes.items() if not k.endswith("/users/")}
                if answer is not None:
                    routes = {f"{API}/users/7001": ({}, answer), **routes}
                code, record = self.run_gate(FakeTransport(routes))
                self.assertEqual((code, record["decision"]), (1, "pending"), record)
                self.assertEqual(record["approved_by"], [])

    def test_approvals_kept_across_pushes_warn(self):
        # GitLab's approval note names no commit, so the gate binds it by time; a project that keeps approvals on a
        # push lets its own merge check count an approval of an older head.
        _, record = self.run_gate(self.transport(settings={"reset_approvals_on_push": False}))
        self.assertEqual(record["decision"], "pass")
        self.assertIn("merge_approval.survives_push", [f["code"] for f in record["findings"]])
        _, record = self.run_gate(self.transport(settings={"reset_approvals_on_push": True}))
        self.assertNotIn("merge_approval.survives_push", [f["code"] for f in record["findings"]])


if __name__ == "__main__":
    unittest.main()
