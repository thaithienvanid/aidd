"""The GitHub adapter end to end: a real git repository with a pull request ref, and a fake GitHub API."""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from helpers import ROOT, FakeTransport, git  # noqa: F401  (ROOT puts src on sys.path)

from aidd import github, http

API = "https://api.github.test"
CONFIG = """aidd_version = "1.0.0"
profile = "team"

[owners]
approvers = ["lead"]

[[tests]]
name = "unit"
command = ["{py}", "-c", "print('ok')"]
"""
BODY = """Fix a typo.

```toml aidd
route = "minor"
type = "docs"
confidence = "high"
scope = ["docs/guide.md"]
rollback = "Revert the PR."
assisted_by = []

[risk]
summary = "Fixes a typo."
dimensions = []
reversible = true
```
"""


@unittest.skipUnless(shutil.which("git"), "git is required")
class GitHubEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        origin, self.work = t / "origin.git", t / "work"
        git(t, "init", "-q", "--bare", "-b", "main", str(origin))
        git(t, "init", "-q", "-b", "main", str(self.work))
        for k, v in (("user.email", "alice@example.com"), ("user.name", "Alice"), ("commit.gpgsign", "false")):
            git(self.work, "config", k, v)
        self.py = sys.executable.replace("\\", "/")
        (self.work / ".aidd").mkdir()
        (self.work / ".aidd/config.toml").write_text(CONFIG.format(py=self.py), encoding="utf-8")
        (self.work / "docs").mkdir()
        (self.work / "docs/guide.md").write_text("Teh guide.\n", encoding="utf-8")
        git(self.work, "add", ".")
        git(self.work, "commit", "-qm", "base")
        git(self.work, "remote", "add", "origin", str(origin))
        git(self.work, "push", "-q", "origin", "main")
        self.base = git(self.work, "rev-parse", "HEAD")
        git(self.work, "checkout", "-qb", "fix")
        (self.work / "docs/guide.md").write_text("The guide.\n", encoding="utf-8")
        git(self.work, "commit", "-qam", "Fix typo")
        self.head = git(self.work, "rev-parse", "HEAD")
        git(self.work, "push", "-q", "origin", f"{self.head}:refs/pull/1/head")
        git(self.work, "checkout", "-q", "main")
        blob = io.BytesIO()
        with zipfile.ZipFile(blob, "w") as zf:
            zf.writestr(
                "evidence.json",
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
            )
        self.zip = blob.getvalue()
        self.event = t / "event.json"
        self.event.write_text(json.dumps({"pull_request": {"number": 1}}), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def transport(self, reviewer="lead", timeline=(), comments=()):
        pr = {
            "number": 1,
            "head": {"sha": self.head, "ref": "fix", "repo": {"full_name": "o/r", "owner": {"login": "o"}}},
            "base": {"ref": "main"},
            "user": {"login": "alice"},
            "body": BODY,
            "draft": False,
            "commits": 1,
            "created_at": "2026-09-25T09:00:00Z",
            "html_url": "https://github.test/o/r/pull/1",
        }
        run = {
            "id": 9,
            "name": "aidd-tests",
            "status": "completed",
            "conclusion": "success",
            "created_at": "2026-09-25T09:10:00Z",
            "path": ".github/workflows/aidd-tests.yml",
            "event": "pull_request",
            "head_sha": self.head,
            "head_branch": "fix",
            "head_repository": {"full_name": "o/r"},
            "html_url": "https://github.test/run/9",
        }
        commit = {
            "sha": self.head,
            "author": {"login": "alice"},
            "committer": {"login": "alice"},
            "parents": [{"sha": self.base}],
            "commit": {
                "message": "Fix typo",
                "author": {"email": "alice@example.com"},
                "committer": {"email": "alice@example.com", "date": "2026-09-25T09:05:00Z"},
                "verification": {"verified": True},
            },
        }
        # FakeTransport matches by prefix in insertion order: the most specific routes come first.
        return FakeTransport(
            {
                f"{API}/repos/o/r/pulls/1/commits": ({}, [commit]),
                f"{API}/repos/o/r/pulls/1/reviews": (
                    {},
                    [{"user": {"login": reviewer}, "state": "APPROVED", "commit_id": self.head, "submitted_at": "2026-09-25T10:00:00Z"}],
                ),
                f"{API}/repos/o/r/pulls/1": ({}, pr),
                f"{API}/repos/o/r/issues/1/comments": ({}, list(comments)),
                f"{API}/repos/o/r/issues/1/timeline": ({}, list(timeline)),
                f"{API}/repos/o/r/pulls?": ({}, [pr]),
                f"{API}/repos/o/r/actions/workflows/aidd-tests.yml/runs": ({}, {"workflow_runs": [run]}),
                f"{API}/repos/o/r/actions/runs/9/artifacts": ({}, {"artifacts": [{"name": "aidd-evidence", "archive_download_url": "https://dl.test/9.zip"}]}),
                "https://dl.test/9.zip": ({}, self.zip),
                f"{API}/repos/o/r/commits/{self.head}/check-suites": ({}, {"check_suites": []}),
                f"{API}/repos/o/r/commits/{self.head}/pulls": ({}, [pr | {"state": "open"}]),
                f"{API}/repos/o/r/statuses/": ({}, {}),
                f"{API}/repos/o/r": ({}, {"default_branch": "main"}),
            }
        )

    def run_gate(self, transport, **flags):
        env = {
            "GITHUB_REPOSITORY": "o/r",
            "GITHUB_EVENT_PATH": str(self.event),
            "GITHUB_API_URL": API,
            "GITHUB_TOKEN": "t",
            "GITHUB_RUN_ID": "5",
            "AIDD_PROTECTED_BRANCHES": "",
            "GITHUB_STEP_SUMMARY": "",
            "AIDD_ORG_PRESET": "",
            "AIDD_MODE": "",
        }
        record = Path(self.tmp.name) / "record.json"
        with (
            mock.patch.dict(os.environ, env),
            mock.patch.object(http, "request", transport),
            mock.patch.object(github, "_fetch", lambda cwd, token, refspecs: git(cwd, "fetch", "-q", "origin", *refspecs)),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            code = github.gate(cwd=str(self.work), record_out=str(record), **flags)
        return code, json.loads(record.read_text(encoding="utf-8")) if record.exists() else None

    def test_an_approved_minor_change_passes_and_posts(self):
        t = self.transport()
        code, record = self.run_gate(t)
        self.assertEqual((code, record["decision"]), (0, "pass"), record)
        posts = [c[3] for c in t.calls if c[0] == "POST"]
        self.assertEqual((posts[0]["state"], posts[0]["context"]), ("success", "aidd/gate"))

    def test_a_failure_before_evaluation_still_posts_an_error(self):
        # A crash while reading the protected branches must not leave an older success standing.
        t = self.transport()

        def down(*a, **k):
            raise http.HttpError(502, f"{API}/repos/o/r/branches", "bad gateway")

        with mock.patch.object(github, "protected_branches", down):
            code, _ = self.run_gate(t)
        posts = [c[3] for c in t.calls if c[0] == "POST"]
        self.assertEqual(code, 2)
        self.assertEqual([(p["state"], p["context"]) for p in posts], [("error", "aidd/gate")])

    def test_retargeting_the_base_voids_an_earlier_approval(self):
        # The approval (10:00) predates the move to another base (10:30): it approved a different diff.
        t = self.transport(timeline=[{"event": "base_ref_changed", "created_at": "2026-09-25T10:30:00Z"}])
        _, record = self.run_gate(t)
        self.assertEqual(record["decision"], "pending")
        self.assertEqual(record["approved_by"], [])

    def test_the_author_cannot_approve(self):
        t = self.transport(reviewer="alice")
        _, record = self.run_gate(t)
        self.assertEqual(record["decision"], "pending")
        self.assertEqual([c[3]["state"] for c in t.calls if c[0] == "POST"], ["pending"])

    def test_a_head_that_moved_while_verifying_is_not_posted(self):
        # The decision is for the head it verified; a newer push gets its own run, so this one must not post.
        t = self.transport()
        pr_url = f"{API}/repos/o/r/pulls/1"
        seen = []

        def moving(method, url, **kw):
            status, headers, body = t(method, url, **kw)
            if method == "GET" and url == pr_url:
                seen.append(url)
                if len(seen) > 1:  # build_context read the old head; the pre-post check sees a new one
                    pr = json.loads(body)
                    pr["head"]["sha"] = "f" * 40
                    body = json.dumps(pr).encode()
            return status, headers, body

        code, record = self.run_gate(moving)
        self.assertEqual((code, record["decision"]), (0, "pass"))
        self.assertGreaterEqual(len(seen), 2)
        self.assertEqual([c for c in t.calls if c[0] == "POST"], [])

    def test_the_push_time_never_comes_from_the_commit(self):
        # With no check suite on head, the solo cool-off has no server time and stays pending; the
        # committer date is the author's to set, so it must not stand in.
        seen = []
        real = github.build_context

        def spy(*a, **k):
            seen.append(real(*a, **k))
            return seen[-1]

        with mock.patch.object(github, "build_context", spy):
            self.run_gate(self.transport())
        self.assertIsNone(seen[0]["head_pushed_at"])

    def resolve(self, event: dict) -> str:
        self.event.write_text(json.dumps(event), encoding="utf-8")
        out = Path(self.tmp.name) / "github_output"
        out.write_text("", encoding="utf-8")
        with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": str(out)}):
            self.assertEqual(self.run_gate(self.transport(), resolve_only=True), (0, None))
        return out.read_text(encoding="utf-8")

    def test_resolve_names_the_head_it_concerns(self):
        # The reusable workflow queues gate runs per head commit (its concurrency group), so resolve prints that head:
        # the pull request's current head as the platform reports it, whatever the event carried.
        self.assertEqual(self.resolve({"pull_request": {"number": 1, "head": {"sha": "0" * 40}}}), f"prs=[1]\npr=1\nhead={self.head}\n")
        self.assertEqual(self.resolve({"issue": {"number": 1, "pull_request": {}}}), f"prs=[1]\npr=1\nhead={self.head}\n")

    def test_resolve_names_a_queue_entrys_own_commit(self):
        sha = "c" * 40
        run = {"event": "merge_group", "head_sha": sha, "head_branch": f"gh-readonly-queue/main/pr-1-{self.base}"}
        self.assertEqual(self.resolve({"workflow_run": run}), f"prs=[1]\npr=1\nhead={sha}\n")

    def test_resolve_with_nothing_to_judge_names_no_head(self):
        self.assertEqual(self.resolve({"issue": {"number": 3}}), "prs=[]\npr=\nhead=\n")

    def test_a_comment_posted_through_an_app_is_marked(self):
        # A comment an App posts for a person (a user-to-server token) carries that person's login; GitHub names the
        # App in performed_via_github_app, and the context keeps it, so the gate never counts the comment as theirs.
        comments = [
            {
                "user": {"login": "lead"},
                "body": f"/aidd approve {self.head}",
                "created_at": "2026-09-25T10:00:00Z",
                "performed_via_github_app": {"slug": "an-agent"},
            },
            {"user": {"login": "lead"}, "body": "Looks good.", "created_at": "2026-09-25T10:01:00Z", "performed_via_github_app": None},
        ]
        seen = []
        real = github.build_context

        def spy(*a, **k):
            seen.append(real(*a, **k))
            return seen[-1]

        with mock.patch.object(github, "build_context", spy):
            self.run_gate(self.transport(comments=comments))
        self.assertEqual([c.get("via_app", False) for c in seen[0]["comments"]], [True, False])


if __name__ == "__main__":
    unittest.main()
