"""Merge queues on GitHub: a queue entry's commit is judged by the approvals on the pull request head, its own tests,
and a tree that must be exactly that head merged into the commit the entry was built on. A real git repository with
a queue branch, and a fake GitHub API."""

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


def _commit(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


@unittest.skipUnless(shutil.which("git"), "git is required")
class MergeQueueTests(unittest.TestCase):
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
        (self.work / "README.md").write_text("readme\n", encoding="utf-8")
        self.base = _commit(self.work, "base")
        git(self.work, "remote", "add", "origin", str(origin))
        git(self.work, "push", "-q", "origin", "main")
        git(self.work, "checkout", "-qb", "fix")
        (self.work / "docs/guide.md").write_text("The guide.\n", encoding="utf-8")
        self.head = _commit(self.work, "Fix typo")
        git(self.work, "push", "-q", "origin", f"{self.head}:refs/pull/1/head")
        git(self.work, "checkout", "-q", "main")
        self.event = t / "event.json"

    def tearDown(self):
        self.tmp.cleanup()

    def queue(self, extra: str | None = None, onto: str | None = None) -> tuple[str, str]:
        """Build a queue entry the way GitHub does: the approved head merged onto `onto` (default: the base tip)."""
        parent = onto or self.base
        git(self.work, "checkout", "-q", "--detach", parent)
        git(self.work, "merge", "-q", "--no-ff", "-m", "Merge pull request #1", self.head)
        if extra:
            (self.work / extra).write_text("not approved\n", encoding="utf-8")
            git(self.work, "add", "-A")
            git(self.work, "commit", "-q", "--amend", "--no-edit")
        sha = git(self.work, "rev-parse", "HEAD")
        branch = f"gh-readonly-queue/main/pr-1-{parent}"
        git(self.work, "push", "-q", "origin", f"{sha}:refs/heads/{branch}")
        git(self.work, "checkout", "-q", "main")
        return sha, branch

    def evidence_zip(self, head: str, base: str) -> bytes:
        blob = io.BytesIO()
        with zipfile.ZipFile(blob, "w") as zf:
            result = {"name": "unit", "source": "config", "command": [self.py, "-c", "print('ok')"], "red_green": "green", "exit": 0, "status": "passed"}
            zf.writestr("evidence.json", json.dumps({"aidd_version": "1.0.0", "head_sha": head, "base_sha": base, "results": [result]}))
        return blob.getvalue()

    def transport(self, sha: str, branch: str, *, evidence_base: str | None = None, grouping: str | None = None):
        pr = {
            "number": 1,
            "head": {"sha": self.head, "ref": "fix", "repo": {"full_name": "o/r", "owner": {"login": "o"}}},
            "base": {"ref": "main"},
            "user": {"login": "alice"},
            "body": BODY,
            "draft": False,
            "commits": 1,
            "created_at": "2026-09-25T09:00:00Z",
        }
        run = {
            "id": 9,
            "name": "aidd-tests",
            "status": "completed",
            "conclusion": "success",
            "created_at": "2026-09-25T11:00:00Z",
            "path": ".github/workflows/aidd-tests.yml",
            "event": "merge_group",
            "head_sha": sha,
            "head_branch": branch,
            "head_repository": {"full_name": "o/r"},
        }
        commit = {
            "sha": self.head,
            "author": {"login": "alice"},
            "committer": {"login": "alice"},
            "parents": [{"sha": self.base}],
            "commit": {"message": "Fix typo", "author": {"email": "a@x"}, "committer": {"email": "a@x"}, "verification": {"verified": True}},
        }
        rules = [{"type": "merge_queue", "parameters": {"grouping_strategy": grouping}}] if grouping else []
        return FakeTransport(
            {
                f"{API}/repos/o/r/pulls/1/commits": ({}, [commit]),
                f"{API}/repos/o/r/pulls/1/reviews": (
                    {},
                    [{"user": {"login": "lead"}, "state": "APPROVED", "commit_id": self.head, "submitted_at": "2026-09-25T10:00:00Z"}],
                ),
                f"{API}/repos/o/r/pulls/1": ({}, pr),
                f"{API}/repos/o/r/issues/1/comments": ({}, []),
                f"{API}/repos/o/r/issues/1/timeline": ({}, []),
                f"{API}/repos/o/r/actions/workflows/aidd-tests.yml/runs": ({}, {"workflow_runs": [run]}),
                f"{API}/repos/o/r/actions/runs/9/artifacts": ({}, {"artifacts": [{"name": "aidd-evidence", "archive_download_url": "https://dl.test/9.zip"}]}),
                "https://dl.test/9.zip": ({}, self.evidence_zip(sha, evidence_base or self.base)),
                f"{API}/repos/o/r/commits/{self.head}/check-suites": ({}, {"check_suites": []}),
                f"{API}/repos/o/r/rules/branches/main": ({}, rules),
                f"{API}/repos/o/r/statuses/": ({}, {}),
                f"{API}/repos/o/r": ({}, {"default_branch": "main"}),
            }
        )

    def run_gate(self, transport, event: dict):
        self.event.write_text(json.dumps(event), encoding="utf-8")
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
        record.unlink(missing_ok=True)
        with (
            mock.patch.dict(os.environ, env),
            mock.patch.object(http, "request", transport),
            mock.patch.object(github, "_fetch", lambda cwd, token, refspecs: git(cwd, "fetch", "-q", "origin", *refspecs)),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            code = github.gate(cwd=str(self.work), record_out=str(record))
        return code, json.loads(record.read_text(encoding="utf-8")) if record.exists() else None

    @staticmethod
    def after_tests(sha: str, branch: str) -> dict:
        """The workflow_run event of the aidd-tests run the queue started: how the gate learns of a queue entry."""
        return {"workflow_run": {"event": "merge_group", "head_sha": sha, "head_branch": branch, "pull_requests": []}}

    def posts(self, t):
        return [(c[1].rsplit("/", 1)[-1], c[3]["state"], c[3]["context"]) for c in t.calls if c[0] == "POST"]

    def test_an_entry_that_is_exactly_the_approved_head_passes_on_its_own_commit(self):
        sha, branch = self.queue()
        t = self.transport(sha, branch)
        code, record = self.run_gate(t, self.after_tests(sha, branch))
        self.assertEqual((code, record["decision"]), (0, "pass"), record)
        # Approvals bind to the pull request head; the status goes on the merge-group commit.
        self.assertEqual((record["head_sha"], record["merge_group_sha"]), (self.head, sha))
        self.assertEqual(self.posts(t), [(sha, "success", "aidd/gate")])

    def test_the_merge_group_event_itself_resolves_the_same_entry(self):
        sha, branch = self.queue()
        event = {"merge_group": {"head_sha": sha, "head_ref": f"refs/heads/{branch}", "base_ref": "refs/heads/main", "base_sha": self.base}}
        self.assertEqual(github.pr_numbers(event, None, "o/r"), [1])  # type: ignore[arg-type]
        code, record = self.run_gate(self.transport(sha, branch), event)
        self.assertEqual(record["decision"], "pass", record)

    def test_an_entry_holding_an_unapproved_change_fails(self):
        sha, branch = self.queue(extra="smuggled.txt")
        t = self.transport(sha, branch)
        code, record = self.run_gate(t, self.after_tests(sha, branch))
        self.assertEqual(record["decision"], "fail")
        self.assertIn({"rule": "merge_queue", "level": "fail", "code": "merge_queue.diff_mismatch"}, record["findings"])
        self.assertEqual(self.posts(t), [(sha, "failure", "aidd/gate")])

    def test_evidence_from_the_pull_request_head_does_not_count_in_the_queue(self):
        sha, branch = self.queue()
        t = self.transport(sha, branch)
        # The artifact claims the pull request head: tests on the head never prove the merge-group commit.
        t.routes["https://dl.test/9.zip"] = ({}, self.evidence_zip(self.head, self.base))
        _, record = self.run_gate(t, self.after_tests(sha, branch))
        self.assertEqual(record["decision"], "pending")
        self.assertIn("tests.evidence_other_head", [f["code"] for f in record["findings"]])

    def test_a_stacked_entry_needs_an_all_green_queue(self):
        # Another pull request is ahead in the queue: this entry is built on its commit, not on the base.
        git(self.work, "checkout", "-q", "--detach", self.base)
        (self.work / "README.md").write_text("readme, by pull request #2\n", encoding="utf-8")
        ahead = _commit(self.work, "Merge pull request #2")
        git(self.work, "push", "-q", "origin", f"{ahead}:refs/heads/gh-readonly-queue/main/pr-2-{self.base}")
        git(self.work, "checkout", "-q", "main")
        sha, branch = self.queue(onto=ahead)
        self.assertEqual(github.queue_parent(str(self.work), sha, ahead, self.base), (ahead, True))
        for grouping, decision in ((None, "fail"), ("HEADGREEN", "fail"), ("ALLGREEN", "pass")):
            with self.subTest(grouping=grouping):
                _, record = self.run_gate(self.transport(sha, branch, evidence_base=ahead, grouping=grouping), self.after_tests(sha, branch))
                self.assertEqual(record["decision"], decision, record)
                codes = [f["code"] for f in record["findings"]]
                self.assertEqual("merge_queue.stacked_unverified" in codes, decision == "fail")

    def test_a_branch_name_git_does_not_confirm_falls_back_to_the_base(self):
        sha, _ = self.queue()
        # A parent the name claims but git does not confirm (not an ancestor of the entry) is ignored.
        self.assertEqual(github.queue_parent(str(self.work), sha, "f" * 40, self.base), (self.base, False))

    def test_an_unexpected_queue_event_fails_closed(self):
        with self.assertRaises(ValueError):
            github.merge_group_of({"merge_group": {"head_sha": "a" * 40, "head_ref": "refs/heads/somewhere-else"}})
        self.assertIsNone(github.merge_group_of({"workflow_run": {"event": "pull_request", "head_sha": "a" * 40, "head_branch": "fix"}}))

    def test_a_conflicting_head_has_no_merged_tree(self):
        git(self.work, "checkout", "-q", "main")
        (self.work / "docs/guide.md").write_text("A different guide.\n", encoding="utf-8")
        moved = _commit(self.work, "Edit the guide on main")
        self.assertIsNone(github.merged_tree(str(self.work), moved, self.head))
        self.assertIsNotNone(github.merged_tree(str(self.work), self.base, self.head))


if __name__ == "__main__":
    unittest.main()
