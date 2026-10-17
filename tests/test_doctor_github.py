"""`aidd doctor` on GitHub, best effort: does the default branch's protection let aidd/gate decide?"""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import FakeTransport, git

from aidd.platforms import github
from aidd.kernel import http

API = "https://api.github.com"


@unittest.skipUnless(shutil.which("git"), "git is required")
class ProtectionChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "remote", "add", "origin", "git@github.com:o/r.git")

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, rules, ruleset=None):
        routes = {f"{API}/repos/o/r/rules/branches/main": ({}, rules)}
        if ruleset is not None:
            routes[f"{API}/repos/o/r/rulesets/7"] = ({}, ruleset)
        routes[f"{API}/repos/o/r"] = ({}, {"default_branch": "main"})
        with mock.patch.object(http, "request", FakeTransport(routes)):
            return github.protection_checks(str(self.root), client=github.Client("t", API))

    def test_a_review_count_without_the_gate_warns_and_explains_bot_approvals(self):
        out = self.check([{"type": "pull_request", "ruleset_id": 7, "parameters": {"required_approving_review_count": 1}}], ruleset={"bypass_actors": []})
        warns = [m for level, m in out if level == "warn"]
        self.assertTrue(any("do not require the `aidd/gate` status" in m and "aidd never counts" in m and "Copilot" in m for m in warns), out)
        self.assertTrue(any("most recent reviewable push" in m for m in warns), out)

    def test_a_pinned_gate_passes_and_app_bypass_and_headgreen_queues_warn(self):
        rules = [
            {"type": "required_status_checks", "ruleset_id": 7, "parameters": {"required_status_checks": [{"context": "aidd/gate", "integration_id": 42}]}},
            {"type": "pull_request", "ruleset_id": 7, "parameters": {"required_approving_review_count": 1, "require_last_push_approval": True}},
            {"type": "merge_queue", "ruleset_id": 7, "parameters": {"grouping_strategy": "HEADGREEN"}},
        ]
        out = self.check(rules, ruleset={"bypass_actors": [{"actor_type": "Integration", "actor_id": 9}]})
        self.assertIn("ok", [level for level, _ in out])
        warns = " | ".join(m for level, m in out if level == "warn")
        self.assertIn("Only merge non-failing pull requests", warns)
        self.assertIn("lets a GitHub App bypass it", warns)
        self.assertNotIn("most recent reviewable push", warns)

    def test_an_unpinned_gate_warns(self):
        out = self.check([{"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "aidd/gate"}]}}])
        self.assertTrue(any(level == "warn" and "pin it to your aidd App" in m for level, m in out), out)

    def test_offline_it_says_it_skipped(self):
        def down(*a, **k):
            raise OSError("network is unreachable")

        with mock.patch.object(http, "request", down):
            out = github.protection_checks(str(self.root), client=github.Client("t", API))
        self.assertEqual([level for level, _ in out], ["ok"])
        self.assertIn("not checked", out[0][1])

    def test_not_github_and_no_token(self):
        git(self.root, "remote", "set-url", "origin", "https://gitlab.com/o/r.git")
        self.assertEqual(github.protection_checks(str(self.root)), [])
        git(self.root, "remote", "set-url", "origin", "https://github.com/o/r")
        with mock.patch.dict("os.environ", {"GH_TOKEN": "", "GITHUB_TOKEN": ""}), mock.patch.object(shutil, "which", lambda _: None):
            out = github.protection_checks(str(self.root))
        self.assertEqual(out, [("ok", "GitHub protection of o/r not checked: no token (set GH_TOKEN, or `gh auth login`)")])

    def test_offline_it_never_calls_the_api(self):
        """AIDD_OFFLINE=1, and the hooks' AIDD_HOOK_OFFLINE=1, skip the check before any request, token or not."""

        def refuse(*a, **k):
            raise AssertionError("protection_checks reached the network")

        for env in ({"AIDD_OFFLINE": "1"}, {"AIDD_OFFLINE": "0", "AIDD_HOOK_OFFLINE": "1"}):
            with self.subTest(**env), mock.patch.dict("os.environ", {"GH_TOKEN": "t", **env}), mock.patch.object(http, "request", refuse):
                out = github.protection_checks(str(self.root))
            self.assertEqual(out, [("ok", "GitHub protection of o/r not checked: offline (AIDD_OFFLINE=1 or a hook)")])


if __name__ == "__main__":
    unittest.main()
