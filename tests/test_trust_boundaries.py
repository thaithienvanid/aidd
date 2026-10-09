"""Every boundary between the trusted gate job and the untrusted test job fails closed.

Covers the runner's scrubbed environment, `extends` validation before any fetch, the HTTPS-only
opener and its private-address resolver, status checks bound to the change's own branch, the MCP
argument and walk bounds, and the evidence archive's size budget.
"""

import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from unittest import mock

from helpers import IN_GIT_CHECKOUT, ROOT, example, rules

from aidd import github, http, inputs, mcp, repo, report, runner, util
from aidd.verify import Decision, verify


class RunnerIsolationTests(unittest.TestCase):
    def test_runner_scrubs_secrets_preserves_ci_vars(self):
        env = {
            "GITHUB_TOKEN": "ghp_supersecret",
            "GH_TOKEN": "ghp_supersecret2",
            "AIDD_GITLAB_TOKEN": "gl_secret",
            "CI_JOB_TOKEN": "job_secret",
            "ACTIONS_RUNTIME_TOKEN": "art_secret",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "id_secret",
            "GITHUB_ACTIONS": "true",
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_REPOSITORY": "org/repo",
            "GITHUB_RUN_ID": "98765",
            "HOME": "/user/home",
            "PATH": os.environ.get("PATH", "/bin"),
        }
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "test.log"
            cmd = [sys.executable, "-c", "import os, json; print(json.dumps(dict(os.environ)))"]
            with mock.patch.dict(os.environ, env, clear=True):
                r = runner.execute(cmd, cwd=d, log=log, timeout=10)
            self.assertEqual(r["status"], "passed")
            self.assertEqual(r["exit"], 0)
            self.assertGreaterEqual(r["duration_seconds"], 0.0)

            captured = json.loads(log.read_text(encoding="utf-8").strip())
            for secret_key in util.SECRET_ENV:
                self.assertNotIn(secret_key, captured, f"{secret_key} must be scrubbed")
            self.assertEqual(captured.get("GITHUB_ACTIONS"), "true")
            self.assertEqual(captured.get("GITHUB_SERVER_URL"), "https://github.com")
            self.assertEqual(captured.get("GITHUB_REPOSITORY"), "org/repo")
            self.assertEqual(captured.get("GITHUB_RUN_ID"), "98765")
            self.assertIn("PATH", captured)
            self.assertIn("HOME", captured)

    def test_runner_caps_log_size(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "big.log"
            cmd = [sys.executable, "-c", f"import sys; sys.stdout.buffer.write(b'A' * {runner.MAX_LOG_BYTES + 500})"]
            r = runner.execute(cmd, cwd=d, log=log, timeout=10)
            self.assertEqual(r["status"], "passed")
            self.assertLessEqual(log.stat().st_size, runner.MAX_LOG_BYTES + 200)
            self.assertIn(b"... [truncated by aidd runner: log exceeded limit] ...", log.read_bytes())

    def test_security_md_describes_token_stripping(self):
        text = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        self.assertIn("stripped from every test command", text)
        self.assertNotIn("runs PR code without secrets", text)

    def test_security_md_has_a_private_channel_while_the_repository_is_private(self):
        """Private vulnerability reporting needs a public repository; the policy names a fallback, and never an
        address nobody reads."""
        report = (ROOT / "SECURITY.md").read_text(encoding="utf-8").split("## Report a vulnerability", 1)[1].split("\n## ", 1)[0]
        self.assertIn("private vulnerability reporting", report)
        self.assertIn("While this repository is private", report)
        self.assertIn("https://github.com/thaithienvanid", report)
        self.assertIn("Do not open a public issue", report)
        self.assertNotRegex(report, r"[\w.+-]+@[\w-]+\.[\w.]+")


class ExtendsSSRFDefensesTests(unittest.TestCase):
    def test_refuse_file_scheme(self):
        config_text = 'aidd_version = "1.0.0"\nprofile = "solo"\nextends = [{ url = "file:///etc/hosts", sha256 = "' + "0" * 64 + '" }]\n'
        calls = []
        warns = []
        res = inputs.collect_extends(config_text, read=lambda p: None, fetch=lambda u, calls=calls: calls.append(u), warnings=warns)
        self.assertEqual(calls, [])
        self.assertEqual(res, {})
        self.assertTrue(any("refused scheme 'file'" in w for w in warns), warns)

    def test_refuse_https_without_sha256(self):
        config_text = 'aidd_version = "1.0.0"\nprofile = "solo"\nextends = [{ url = "https://example.com/parent.toml" }]\n'
        calls = []
        warns = []
        res = inputs.collect_extends(config_text, read=lambda p: None, fetch=lambda u, calls=calls: calls.append(u), warnings=warns)
        self.assertEqual(calls, [])
        self.assertEqual(res, {})
        self.assertTrue(any("does not match schema" in w for w in warns), warns)

    def test_refuse_non_public_addresses(self):
        bad_ips = [
            ("127.0.0.1", "loopback"),
            ("10.0.0.1", "private"),
            ("169.254.169.254", "link-local"),
            ("::1", "loopback"),
        ]
        for ip, expected_class in bad_ips:
            host_part = f"[{ip}]" if ":" in ip else ip
            config_text = f'aidd_version = "1.0.0"\nprofile = "solo"\nextends = [{{ url = "https://{host_part}/base.toml", sha256 = "{"0" * 64}" }}]\n'
            calls = []
            warns = []
            res = inputs.collect_extends(config_text, read=lambda p: None, fetch=lambda u, calls=calls: calls.append(u), warnings=warns)
            self.assertEqual(calls, [], f"fetch should not be called for {ip}")
            self.assertEqual(res, {})
            self.assertTrue(any(expected_class in w for w in warns), f"expected {expected_class} in {warns}")

    def test_safe_redirect_handler_refuses_https_to_http(self):
        handler = http.SafeRedirectHandler()
        req = urllib.request.Request("https://example.com/start")
        with self.assertRaises(http.HttpError) as cm:
            handler.redirect_request(req, None, 302, "Found", {}, "http://insecure.test/target")
        self.assertIn("refusing redirect from https to non-https", str(cm.exception))

    def test_get_bytes_exceeding_max_bytes_raises(self):
        class MockResp:
            status = 200
            headers = {}

            def __init__(self, data):
                self.data = data

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n=-1):
                if n == -1:
                    return self.data
                return self.data[:n]

        with mock.patch.object(http._OPENER, "open", lambda req, timeout=30: MockResp(b"X" * 200)):
            with self.assertRaises(http.HttpError) as cm:
                http.get_bytes("https://example.com/file", max_bytes=100)
            self.assertIn("response exceeded maximum size of 100 bytes", str(cm.exception))


class StatusChecksHardeningTests(unittest.TestCase):
    def test_missing_head_branch_in_check_suite_rejected(self):
        runs_data = [
            {
                "name": "build",
                "app": {"slug": "github-actions"},
                "status": "completed",
                "conclusion": "success",
                "started_at": "2026-09-25T10:00:00Z",
                "check_suite": {},  # missing head_branch key!
            }
        ]
        client = github.Client("t", "https://api.test", transport=lambda m, u, **kw: (200, {}, json.dumps({"check_runs": runs_data}).encode()))
        states = github._status_checks(client, "o/r", "head_sha", ["build"], apps=["github-actions"], head_ref="feature")
        self.assertEqual(states, {}, "check run without head_branch must be rejected")

    def test_status_checks_picks_newest_by_parsed_instant(self):
        runs_data = [
            # Older run started first (09:00:00), completed later (23:00:00)
            {
                "name": "build",
                "app": {"slug": "github-actions"},
                "status": "completed",
                "conclusion": "failure",
                "started_at": "2026-09-25T09:00:00Z",
                "completed_at": "2026-09-25T23:00:00Z",
                "check_suite": {"head_branch": "feature"},
            },
            # Newer run started later (10:00:00), completed earlier (10:30:00)
            {
                "name": "build",
                "app": {"slug": "github-actions"},
                "status": "completed",
                "conclusion": "success",
                "started_at": "2026-09-25T10:00:00Z",
                "completed_at": "2026-09-25T10:30:00Z",
                "check_suite": {"head_branch": "feature"},
            },
        ]
        client = github.Client("t", "https://api.test", transport=lambda m, u, **kw: (200, {}, json.dumps({"check_runs": runs_data}).encode()))
        states = github._status_checks(client, "o/r", "head_sha", ["build"], apps=["github-actions"], head_ref="feature")
        # 10:00:00Z started run is newest and its conclusion is success
        self.assertEqual(states.get("build"), "success")

    def test_gate_status_checks_skipped_is_pending(self):
        ctx = example("02-normal-feature")
        ctx["base_config"] += '\n[evidence]\nstatus_checks = ["ci/deploy"]\n'
        ctx["status_checks"] = {"ci/deploy": "skipped"}
        d = verify(ctx)
        self.assertEqual(d.decision, "pending")
        self.assertIn("tests", rules(d, "pending"))
        f = next(f for f in d.findings if f.rule == "tests" and f.level == "pending")
        self.assertEqual(f.fix, "the check did not run on this head")


class MCPHardeningTests(unittest.TestCase):
    @unittest.skipUnless(IN_GIT_CHECKOUT, "next runs inside a git repository")
    def test_next_paths_are_paths_never_flags(self):
        is_err, text = mcp.call("assess", {"paths": ["--irreversible"]}, str(ROOT))
        self.assertFalse(is_err, text)
        route = json.loads(text)["route"]
        self.assertEqual(route["route"], "minor")  # a path named --irreversible, not the flag that forces major
        self.assertTrue(mcp.call("assess", {"type": "--help"}, str(ROOT))[0])

    def test_validate_path_outside_repo_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            repo.init(Path(d), profile="solo", ci="none", links=[], harnesses=[])
            is_err, text = mcp.call("validate", {"paths": ["/"]}, d)
            self.assertTrue(is_err)
            self.assertIn("outside the repository", text)

    def test_bounded_directory_walk(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for i in range(15):
                (root / f"spec_{i}.md").write_text("content\n", encoding="utf-8")
            files, stopped = repo._walk_bounded(root, max_files=10)
            self.assertTrue(stopped)
            self.assertEqual(len(files), 10)

    def test_stdin_line_exceeding_cap_returns_parse_error(self):
        big_line = " " * (mcp.MAX_LINE_BYTES + 10) + "\n"
        stdin = io.StringIO(big_line)
        stdout = io.StringIO()
        mcp.serve(stdin=stdin, stdout=stdout, root="/")
        resp = json.loads(stdout.getvalue().strip())
        self.assertEqual(resp["error"]["code"], -32700)

    def test_initialize_does_not_echo_unsupported_version(self):
        req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}}
        resp = mcp.handle(req, "/")
        self.assertNotEqual(resp["result"]["protocolVersion"], "2025-11-25")
        self.assertEqual(resp["result"]["protocolVersion"], "2025-06-18")

    def test_request_with_id_and_no_method_returns_32600(self):
        req = {"jsonrpc": "2.0", "id": 42}
        resp = mcp.handle(req, "/")
        self.assertEqual(resp["error"]["code"], -32600)


class TransportEdgeCasesTests(unittest.TestCase):
    def test_evidence_zip_size_cap_refuses_decompression(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("evidence.json", b"0" * (github.MAX_EVIDENCE_BYTES + 1000))

        client = github.Client("t", "https://api.test")
        client.download = lambda url, **kw: buf.getvalue()
        run = {
            "id": 1,
            "name": "aidd-tests",
            "path": ".github/workflows/aidd-tests.yml",
            "status": "completed",
            "conclusion": "success",
            "created_at": "2026-09-25T10:00:00Z",
            "html_url": "https://github.com/o/r/actions/runs/1",
        }

        def fake_get(p, params=None):
            if "artifacts" in p:
                return {"artifacts": [{"name": "aidd-evidence", "archive_download_url": "https://dl.test/a.zip"}]}
            return {"workflow_runs": [run]}

        client.get = fake_get
        data, _ = github.evidence(client, "o/r", "head_sha", workflow="aidd-tests", artifact="aidd-evidence")
        self.assertIsInstance(data, dict)
        self.assertIn("invalid", data)
        self.assertIn("exceeds", data["invalid"])

    def test_next_link_same_origin_check(self):
        cross_origin_headers = {"link": '<https://attacker.com/next_page>; rel="next"'}
        self.assertIsNone(http.next_link(cross_origin_headers, "https://api.github.com/repos/o/r/pulls"))

        same_origin_headers = {"link": '<https://api.github.com/repos/o/r/pulls?page=2>; rel="next"'}
        self.assertEqual(http.next_link(same_origin_headers, "https://api.github.com/repos/o/r/pulls"), "https://api.github.com/repos/o/r/pulls?page=2")

    def test_post_does_not_retry_502(self):
        calls = []

        class MockResp:
            pass

        def fake_urlopen(req, timeout=30):
            calls.append(req.get_method())
            raise urllib.error.HTTPError(req.full_url, 502, "Bad Gateway", {}, io.BytesIO(b"bad gateway"))

        with mock.patch.object(http._OPENER, "open", fake_urlopen), mock.patch("time.sleep"):
            with self.assertRaises(http.HttpError):
                http.request("POST", "https://api.test/post", data={"test": 1})
        self.assertEqual(len(calls), 1, "non-idempotent POST must not be retried")

    def test_report_event_empty_string_for_none_change(self):
        d = Decision(decision="pass", findings=[], record={"change": None})
        ev = report.event(d, "o/r")
        self.assertEqual(ev["change"], "")

    def test_paginate_strict_raises_page_limit_error(self):
        pages = {
            "https://api.test/items?per_page=100": ({"link": '<https://api.test/items?per_page=100&page=2>; rel="next"'}, json.dumps([{"id": 1}]).encode()),
            "https://api.test/items?per_page=100&page=2": ({}, json.dumps([{"id": 2}]).encode()),
        }
        client = http.JsonClient("t", "https://api.test", transport=lambda m, u, **kw: (200, pages[u][0], pages[u][1]))
        with self.assertRaises(http.PageLimitError):
            client.paginate("/items", limit=1, strict=True)


if __name__ == "__main__":
    unittest.main()
