"""Scale and adoption features: bot standard changes, per-path owners, per-path tests, presets, CLI robustness."""

import io
import shutil
import subprocess
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from helpers import run_cli as cli_run

from aidd.kernel import http

FEATURE = "02-normal-feature"
OWNERS = '  paths:\n    - paths: ["src/checkout/**"]\n      approvers: ["@checkout-owner"]\n'


class HttpTests(unittest.TestCase):
    def test_rate_limit_is_retried(self):
        calls = []

        class Resp(io.BytesIO):
            status = 200
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake(req, timeout=30):
            calls.append(req.full_url)
            if len(calls) == 1:
                raise urllib.error.HTTPError(req.full_url, 429, "slow down", {"Retry-After": "1"}, io.BytesIO(b"{}"))
            return Resp(b'{"ok": true}')

        with mock.patch.object(http._shared_opener(True), "open", fake), mock.patch("time.sleep"):
            self.assertEqual(http.get_bytes("https://api.test/x", max_bytes=1024), b'{"ok": true}')
        self.assertEqual(len(calls), 2)

    def test_network_errors_become_http_errors(self):
        def fake(req, timeout=30):
            raise urllib.error.URLError("no route")

        with mock.patch.object(http._shared_opener(True), "open", fake), mock.patch("time.sleep"):
            with self.assertRaises(http.HttpError):
                http.get_bytes("https://api.test/x", max_bytes=1024)

    def test_every_request_needs_a_byte_cap_and_a_longer_answer_is_refused(self):
        with self.assertRaises(TypeError):
            http.get_bytes("https://api.test/x")  # type: ignore[call-arg]
        with self.assertRaises(TypeError):
            http.request("GET", "https://api.test/x")  # type: ignore[call-arg]
        with self.assertRaises(ValueError):
            http.get_bytes("https://api.test/x", max_bytes=-1)

        class Resp(io.BytesIO):
            status = 200
            headers: dict = {}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake(req, timeout=30):
            return Resp(b"x" * 100)

        with mock.patch.object(http._shared_opener(True), "open", fake):
            self.assertEqual(http.get_bytes("https://api.test/x", max_bytes=100), b"x" * 100)
            with self.assertRaisesRegex(http.HttpError, "exceeded maximum size of 99 bytes"):
                http.get_bytes("https://api.test/x", max_bytes=99)


@unittest.skipUnless(shutil.which("git"), "git is required")
class CliRobustnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)  # after a test's chdir is undone: Windows cannot remove the working directory
        self.root = Path(self.tmp.name)
        run = lambda *a: subprocess.run(["git", *a], cwd=self.root, check=True, capture_output=True)  # noqa: E731
        run("init", "-q", "-b", "master")
        run("config", "user.email", "a@example.com")
        run("config", "user.name", "A")
        run("config", "commit.gpgsign", "false")
        (self.root / ".aidd").mkdir()
        (self.root / ".aidd/config.yaml").write_text('aidd_version: "1.0.0"\nprofile: solo\n', encoding="utf-8")
        (self.root / "docs").mkdir()
        (self.root / "docs/a.md").write_text("a\n", encoding="utf-8")
        run("add", ".")
        run("commit", "-qm", "base")
        run("checkout", "-qb", "feature")
        (self.root / "docs/a.md").write_text("b\n", encoding="utf-8")
        run("commit", "-qam", "edit")

    def test_errors_exit_two(self):
        self.assertEqual(cli_run("validate", str(self.root / "missing.md"))[0], 2)
        self.assertEqual(cli_run("new", "spec", "../escape", "--title", "x")[0], 2)
        self.assertEqual(cli_run("risk")[0], 2)  # no --paths, --command, --action, or --list


if __name__ == "__main__":
    unittest.main()
