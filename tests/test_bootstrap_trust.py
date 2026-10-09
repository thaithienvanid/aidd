"""A change that adds the first config never brings the commands or trust it is judged by.

When the base branch has no .aidd/config.toml, the gate reads the change's config only for display: its Policy
command must not run in the trusted gate job, and its evidence and status-check settings must not be trusted. Each
adapter (local, GitHub, GitLab) is checked against a real git repository.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import FakeTransport, git

from aidd import github, gitlab, inputs, localctx, runner

PY = sys.executable.replace("\\", "/")
CONFIG = """aidd_version = "1.0.0"
profile = "team"

[owners]
approvers = ["@lead"]

[policy]
command = ["{py}", "-c", "open(r'{marker}', 'w').write('ran'); print('allow')"]

[evidence]
status_checks = ["ci"]
"""
BODY = """```toml aidd
route = "minor"
type = "docs"
confidence = "high"
scope = ["docs/guide.md"]
rollback = "Revert."
assisted_by = []

[risk]
summary = "Typo."
dimensions = []
reversible = true
```
"""


@unittest.skipUnless(shutil.which("git"), "git is required")
class BootstrapConfigIsNeverTrustedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.marker = t / "policy-ran"
        origin, self.work = t / "origin.git", t / "work"
        git(t, "init", "-q", "--bare", "-b", "main", str(origin))
        git(t, "init", "-q", "-b", "main", str(self.work))
        (self.work / "docs").mkdir()
        (self.work / "docs/guide.md").write_text("Teh guide.\n", encoding="utf-8")
        git(self.work, "add", ".")
        git(self.work, "commit", "-qm", "base without a config")
        git(self.work, "remote", "add", "origin", str(origin))
        git(self.work, "push", "-q", "origin", "main")
        self.base = git(self.work, "rev-parse", "HEAD")
        git(self.work, "checkout", "-qb", "fix")
        (self.work / ".aidd").mkdir()
        (self.work / ".aidd/config.toml").write_text(CONFIG.format(py=PY, marker=self.marker.as_posix()), encoding="utf-8")
        (self.work / "docs/guide.md").write_text("The guide.\n", encoding="utf-8")
        git(self.work, "add", ".")
        git(self.work, "commit", "-qm", "add a config and fix a typo")
        self.head = git(self.work, "rev-parse", "HEAD")
        git(self.work, "push", "-q", "origin", f"{self.head}:refs/pull/1/head", f"{self.head}:refs/merge-requests/1/head")

    def test_declared_inputs_returns_the_head_config_only_for_display(self):
        decl = inputs.declared_inputs(str(self.work), self.base, self.head, BODY)
        self.assertIsNone(decl["config"])
        self.assertIsNotNone(decl["bootstrap_config"])
        self.assertTrue(decl["bootstrap_config"].policy_command)
        self.assertIsNone(decl["base_config"])
        self.assertIn(".aidd/config.toml", decl["head_files"])
        self.assertEqual(decl["pools"], [])  # the change's own approvers never reach team lookups

    def test_a_base_config_is_the_config_in_force(self):
        git(self.work, "checkout", "-q", "main")
        (self.work / ".aidd").mkdir(exist_ok=True)
        (self.work / ".aidd/config.toml").write_text(CONFIG.format(py=PY, marker=self.marker.as_posix()), encoding="utf-8")
        git(self.work, "add", ".")
        git(self.work, "commit", "-qm", "adopt aidd")
        tip = git(self.work, "rev-parse", "HEAD")
        decl = inputs.declared_inputs(str(self.work), tip, self.head, BODY)
        self.assertIsNotNone(decl["config"])
        self.assertIsNone(decl["bootstrap_config"])

    def test_local_preflight_runs_no_head_policy(self):
        ctx = localctx.build(repo=str(self.work), base="main", head=self.head, body=BODY)
        self.assertEqual(ctx["policy"], {"result": "unbound"})
        self.assertFalse(self.marker.exists(), "the change's own Policy command ran")

    def test_the_test_runner_may_still_use_the_changes_own_suite(self):
        cfg, _, _, _ = runner._declarations(str(self.work), self.base, self.head, self.base, spec=None, body=BODY)
        self.assertEqual(cfg.get("evidence", "status_checks"), ["ci"])

    def test_github_gate_runs_no_head_policy_and_trusts_no_head_status_checks(self):
        api = "https://api.github.test"
        pr = {
            "number": 1,
            "head": {"sha": self.head, "ref": "fix", "repo": {"full_name": "o/r", "owner": {"login": "o"}}},
            "base": {"ref": "main"},
            "user": {"login": "alice"},
            "body": BODY,
            "commits": 1,
        }
        t = FakeTransport(
            {
                f"{api}/repos/o/r/pulls/1/commits": ({}, []),
                f"{api}/repos/o/r/pulls/1/reviews": ({}, []),
                f"{api}/repos/o/r/pulls/1": ({}, pr),
                f"{api}/repos/o/r/issues/1/comments": ({}, []),
                f"{api}/repos/o/r/issues/1/timeline": ({}, []),
                f"{api}/repos/o/r/pulls?": ({}, [pr]),
                f"{api}/repos/o/r/actions/workflows/": ({}, {"workflow_runs": []}),
                f"{api}/repos/o/r/commits/{self.head}/check-suites": ({}, {"check_suites": []}),
                f"{api}/repos/o/r/commits/{self.head}/check-runs": ({}, {"check_runs": [{"name": "ci", "conclusion": "success"}]}),
            }
        )
        client = github.Client("t", api, transport=t)
        with mock.patch.object(github, "_fetch", lambda cwd, token, refspecs: git(cwd, "fetch", "-q", "origin", *refspecs)):
            ctx = github.build_context(client, "o/r", 1, cwd=str(self.work))
        self.assertEqual(ctx["policy"], {"result": "unbound"})
        self.assertFalse(self.marker.exists(), "the change's own Policy command ran in the trusted gate job")
        self.assertEqual(ctx["status_checks"], {})
        self.assertFalse([c for c in t.calls if "check-runs" in c[1]], "head status_checks were queried")
        self.assertIsNone(ctx["base_config"])

    def test_gitlab_gate_runs_no_head_policy(self):
        api = "https://gitlab.test/api/v4"
        t = FakeTransport(
            {
                f"{api}/projects/7/merge_requests/1/commits": ({}, []),
                f"{api}/projects/7/merge_requests/1/notes": ({}, []),
                f"{api}/projects/7/merge_requests/1": (
                    {},
                    {"sha": self.head, "target_branch": "main", "description": BODY, "author": {"username": "alice"}},
                ),
                f"{api}/projects/7/approvals": ({}, {}),
            }
        )
        ctx = gitlab.build_context(gitlab.Client("t", api, transport=t), "7", 1, cwd=str(self.work))
        self.assertEqual(ctx["policy"], {"result": "unbound"})
        self.assertFalse(self.marker.exists(), "the change's own Policy command ran in the trusted gate job")


if __name__ == "__main__":
    unittest.main()
