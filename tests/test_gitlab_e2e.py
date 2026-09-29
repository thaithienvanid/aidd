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

from helpers import ROOT, FakeTransport, git  # noqa: F401  (ROOT puts src on sys.path)

from aidd import gitlab, http

API = "https://gitlab.test/api/v4"
CONFIG = """aidd_version = "1.0.0"
profile = "team"

[owners]
approvers = ["@lead"]

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
rollback = "Revert the MR."
assisted_by = []

[risk]
summary = "Fixes a typo."
dimensions = []
reversible = true
```
"""


@unittest.skipUnless(shutil.which("git"), "git is required")
class GitLabEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.origin, self.work = t / "origin.git", t / "work"
        git(t, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(t, "init", "-q", "-b", "main", str(self.work))
        for k, v in (("user.email", "alice@example.com"), ("user.name", "Alice"), ("commit.gpgsign", "false")):
            git(self.work, "config", k, v)
        (self.work / ".aidd").mkdir()
        self.py = sys.executable.replace("\\", "/")
        (self.work / ".aidd/config.toml").write_text(CONFIG.format(py=self.py), encoding="utf-8")
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
                            "phase": "green",
                            "exit": 0,
                            "status": "passed",
                            "duration_s": 0.1,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def transport(self, approver="lead", approved_at="2026-09-25T10:05:00Z", committers_blocked=True):
        return FakeTransport(
            {
                f"{API}/projects/7/merge_requests/1/commits": (
                    {},
                    [{"id": self.head, "author_email": "alice@example.com", "committer_email": "alice@example.com", "message": "Fix typo"}],
                ),
                f"{API}/projects/7/merge_requests/1/notes": (
                    {},
                    [{"system": True, "body": "approved this merge request", "author": {"username": approver}, "created_at": approved_at}],
                ),
                f"{API}/projects/7/merge_requests/1": (
                    {},
                    {"sha": self.head, "target_branch": "main", "description": BODY, "author": {"username": "alice"}, "created_at": "2026-09-25T09:00:00Z"},
                ),
                f"{API}/projects/7/approvals": (
                    {},
                    {"merge_requests_disable_committers_approval": committers_blocked, "merge_requests_author_approval": False},
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
        with mock.patch.dict(os.environ, {**base_env, **env}), mock.patch.object(http, "request", transport), contextlib.redirect_stdout(io.StringIO()):
            code = gitlab.gate(cwd=str(self.work), evidence_path=str(self.evidence), record_out=str(record), post=True)
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


if __name__ == "__main__":
    unittest.main()
