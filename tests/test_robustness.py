"""Robustness: bad input, slow or hostile subprocesses, and untrusted text never crash aidd or leak a secret.

Each class pins one way aidd stays bounded and fails safe."""

import base64
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import git, make_repo

from aidd import github, gitutil, guard, http, inputs, mcp, model, policy, repo, runner, util

PY = sys.executable


class MCPServerSurvivesBadArgumentsTests(unittest.TestCase):
    """argparse raises SystemExit on bad input; the MCP server survives it."""

    def serve(self, *messages):
        stdin = io.StringIO("".join(json.dumps(m) + "\n" for m in messages))
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q", "-b", "main")
            repo.init(Path(d), profile="solo", ci="none", links=[], harnesses=[])
            code = mcp.serve(stdin=stdin, stdout=stdout, root=d)
        return code, [json.loads(line) for line in stdout.getvalue().splitlines()]

    def test_an_option_like_value_then_ping_is_still_answered(self):
        bad = [
            {"name": "assess", "arguments": {"type": "--help"}},
            {"name": "assess", "arguments": {"dimension": ["--bogus"]}},
            {"name": "describe", "arguments": {"type": "-h"}},
            {"name": "approval_line", "arguments": {"spec": "-h"}},
            {"name": "gate", "arguments": {"spec": "--help"}},
        ]
        messages = [{"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": p} for i, p in enumerate(bad)]
        messages.append({"jsonrpc": "2.0", "id": 99, "method": "ping"})
        code, replies = self.serve(*messages)
        self.assertEqual(code, 0)
        self.assertEqual([r["id"] for r in replies], [0, 1, 2, 3, 4, 99])
        self.assertEqual(replies[-1]["result"], {})
        for r in replies[:-1]:
            self.assertIn("result", r, r)
        self.assertTrue(replies[3]["result"]["isError"])
        for r in replies[:2]:  # not an enum value: an error answer, never a flag
            self.assertTrue(r["result"]["isError"], r)

    def test_argparse_exit_becomes_an_error_answer(self):
        code, text = mcp._cli(["describe", "--no-such-flag"], ".")
        self.assertEqual(code, 2)
        self.assertIn("unrecognized arguments", text)


class PolicyOutputAndProcessGroupTests(unittest.TestCase):
    """Invalid UTF-8 on a Policy's stdout never crashes the gate, and a timeout kills the whole process group."""

    def test_invalid_utf8_is_a_clean_unreachable(self):
        got = policy.run([PY, "-c", "import sys; sys.stdout.buffer.write(b'\\xff\\xfe allow\\n')"])
        self.assertEqual(got["result"], "unreachable")

    def test_valid_output_still_answers(self):
        self.assertEqual(policy.run([PY, "-c", "print('deny frozen')"])["result"], "deny")

    @unittest.skipUnless(hasattr(os, "killpg"), "process groups are POSIX")
    def test_a_timeout_kills_the_grandchildren_too(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / "survived"
            child = f"import time; time.sleep(1.5); open({str(marker)!r}, 'w').write('x')"
            parent = f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(30)"
            t = time.monotonic()
            got = policy.run([PY, "-c", parent], timeout=0.5)
            self.assertLess(time.monotonic() - t, 10)
            self.assertEqual(got, {"result": "unreachable", "detail": "timed out after 0.5s"})
            time.sleep(2.0)
            self.assertFalse(marker.exists(), "a grandchild of the Policy command outlived its timeout")

    @unittest.skipUnless(hasattr(os, "killpg"), "process groups are POSIX")
    def test_run_bounded_without_capture_kills_the_group(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / "survived"
            child = f"import time; time.sleep(1.5); open({str(marker)!r}, 'w').write('x')"
            parent = f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(30)"
            code, _, _ = util.run_bounded([PY, "-c", parent], timeout=0.5, capture=False)
            self.assertIsNone(code)
            time.sleep(2.0)
            self.assertFalse(marker.exists())


class GitCallsAreBoundedTests(unittest.TestCase):
    """Every git call has a timeout, and a git failure is a GitError, never a leaked CalledProcessError."""

    def test_a_timeout_is_a_git_error_for_every_wrapper(self):
        def hang(*a, **k):
            self.assertIn("timeout", k)
            raise subprocess.TimeoutExpired(a[0], k["timeout"])

        with mock.patch.object(gitutil.subprocess, "run", hang):
            for call in (
                lambda: gitutil.run(["status"]),
                lambda: gitutil.ok(["status"]),
                lambda: gitutil.show("HEAD", "x"),
                lambda: gitutil.fetch(".", ["main"]),
            ):
                with self.assertRaises(gitutil.GitError) as cm:
                    call()
                self.assertIn("timed out", str(cm.exception))

    def test_fetch_abandons_a_stalled_transfer(self):
        seen = {}

        def fake(argv, **k):
            seen.update(argv=argv, env=k["env"], timeout=k["timeout"])
            return subprocess.CompletedProcess(argv, 0, b"", b"")

        with mock.patch.object(gitutil.subprocess, "run", fake):
            gitutil.fetch(".", ["+refs/heads/main:refs/aidd/base"])
        self.assertEqual(seen["env"]["GIT_HTTP_LOW_SPEED_LIMIT"], "1000")
        self.assertEqual(seen["env"]["GIT_HTTP_LOW_SPEED_TIME"], "60")
        self.assertEqual(seen["timeout"], gitutil.DEFAULT_TIMEOUT)

    def test_materialize_raises_git_error_for_a_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q", "-b", "main")
            git(d, "commit", "-q", "--allow-empty", "-m", "x")
            head = git(d, "rev-parse", "HEAD")
            with self.assertRaises(gitutil.GitError):
                runner._materialize(d, head, ["tests/missing.py"], str(Path(d) / "out"))

    def test_dirty_names_paths_exactly(self):
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q", "-b", "main")
            for name in ("a b.txt", "caf\u00e9.txt", "old.txt"):
                (Path(d) / name).write_text("1\n", encoding="utf-8")
            git(d, "add", ".")
            git(d, "commit", "-qm", "x")
            (Path(d) / "a b.txt").write_text("2\n", encoding="utf-8")
            (Path(d) / "caf\u00e9.txt").write_text("2\n", encoding="utf-8")
            git(d, "mv", "old.txt", "new.txt")
            self.assertEqual(sorted(gitutil.dirty(d)), ["a b.txt", "caf\u00e9.txt", "new.txt"])


class GitHubAdapterCoverageTests(unittest.TestCase):
    def test_fetch_never_puts_the_token_on_argv(self):
        token = "ghs_SECRETSECRETSECRET"
        seen = {}

        def fake(argv, **k):
            seen.update(argv=argv, env=k["env"])
            return subprocess.CompletedProcess(argv, 0, b"", b"")

        with mock.patch.object(gitutil.subprocess, "run", fake), mock.patch.dict(os.environ, {"GITHUB_SERVER_URL": "https://github.com"}):
            github._fetch(".", token, ["+refs/pull/1/head:refs/aidd/pr-head"])
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        self.assertFalse([a for a in seen["argv"] if token in a or basic in a], seen["argv"])
        self.assertEqual(seen["env"]["GIT_CONFIG_VALUE_0"], f"AUTHORIZATION: basic {basic}")
        self.assertEqual(seen["env"]["GIT_CONFIG_KEY_0"], "http.https://github.com/.extraheader")
        self.assertEqual(seen["env"]["GIT_HTTP_LOW_SPEED_TIME"], "60")

    def test_a_failed_fetch_message_never_shows_the_token(self):
        token = "ghs_SECRETSECRETSECRET"

        def fake(argv, **k):
            return subprocess.CompletedProcess(argv, 128, b"", b"fatal: could not read from remote")

        with mock.patch.object(gitutil.subprocess, "run", fake), self.assertRaises(gitutil.GitError) as cm:
            github._fetch(".", token, ["x"])
        self.assertNotIn(token, str(cm.exception))


@unittest.skipIf(os.name == "nt", "the fake gh is a shell script")
class VerifyAttestationTests(unittest.TestCase):
    """github.verify_attestation: the argv it passes to `gh`, the token in the environment only, and its exit handling."""

    def fake_gh(self, d: str, exit_code: int, stderr: str = "") -> Path:
        log = Path(d) / "argv.json"
        gh = Path(d) / "gh"
        gh.write_text(
            f"#!{PY}\nimport json, os, sys\n"
            f"json.dump({{'argv': sys.argv[1:], 'token': os.environ.get('GH_TOKEN')}}, open({str(log)!r}, 'w'))\n"
            f"sys.stderr.write({stderr!r})\nsys.exit({exit_code})\n",
            encoding="utf-8",
        )
        gh.chmod(0o755)
        return log

    def test_a_verified_attestation(self):
        with tempfile.TemporaryDirectory() as d:
            log = self.fake_gh(d, 0)
            with mock.patch.dict(os.environ, {"PATH": d}):
                why = github.verify_attestation(b"{}", "o/r", "o/r/.github/workflows/aidd-tests.yml", "tok")
            self.assertIsNone(why)
            seen = json.loads(log.read_text(encoding="utf-8"))
        self.assertEqual(seen["argv"][:2], ["attestation", "verify"])
        self.assertTrue(seen["argv"][2].endswith("evidence.json"))
        self.assertEqual(seen["argv"][3:], ["--repo", "o/r", "--signer-workflow", "o/r/.github/workflows/aidd-tests.yml", "--format", "json"])
        self.assertEqual(seen["token"], "tok")
        self.assertNotIn("tok", seen["argv"])

    def test_a_rejected_attestation_says_why(self):
        with tempfile.TemporaryDirectory() as d:
            self.fake_gh(d, 1, "no matching attestations\\xff")
            with mock.patch.dict(os.environ, {"PATH": d}):
                why = github.verify_attestation(b"{}", "o/r", "wf", "tok")
        self.assertIn("no valid attestation from wf", why)
        self.assertIn("no matching attestations", why)

    def test_no_gh_on_the_runner(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"PATH": d}):
            self.assertIn("gh CLI is not on the runner", github.verify_attestation(b"{}", "o/r", "wf", "tok"))

    def test_a_hung_gh_is_a_reason_not_a_crash(self):
        with tempfile.TemporaryDirectory() as d:
            self.fake_gh(d, 0)
            with mock.patch.dict(os.environ, {"PATH": d}), mock.patch.object(github.subprocess, "run", side_effect=subprocess.TimeoutExpired("gh", 120)):
                why = github.verify_attestation(b"{}", "o/r", "wf", "tok")
        self.assertIn("did not finish", why)


class RunnerValidatesTheSpecTests(unittest.TestCase):
    """The runner reads the Spec with its schema, so a test name such as `../../x` never chooses where a log is written."""

    def test_a_spec_that_fails_its_schema_runs_nothing(self):
        from test_git_e2e import CONFIG, SPEC

        py = PY.replace("\\", "/")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            root.mkdir()
            marker = Path(d) / "ran"
            git(root, "init", "-q", "-b", "main")
            (root / ".aidd").mkdir()
            (root / ".aidd/config.toml").write_text(CONFIG.format(py=py), encoding="utf-8")
            git(root, "add", ".")
            git(root, "commit", "-qm", "base")
            git(root, "checkout", "-qb", "feature")
            (root / "specs").mkdir()
            (root / "checks").mkdir()
            (root / "checks/test_greet.py").write_text("print('x')\n", encoding="utf-8")
            spec = SPEC.format(py=py).replace('name = "greet"', 'name = "../../../../escape"')
            spec = spec.replace('command = ["' + py + '", "checks/test_greet.py"]', f"command = [{py!r}, '-c', \"open({str(marker)!r}, 'w')\"]")
            (root / "specs/SPEC-1.md").write_text(spec, encoding="utf-8")
            git(root, "add", ".")
            git(root, "commit", "-qm", "spec")
            with self.assertRaises(model.ModelError) as cm:
                runner.run_tests(repo=str(root), base="main", out_dir=str(root / "aidd-evidence"))
            self.assertIn("name", str(cm.exception))
            self.assertFalse(marker.exists())
            self.assertFalse((Path(d) / "escape.log").exists())

    def test_log_path_refuses_a_name_that_climbs_out(self):
        with tempfile.TemporaryDirectory() as d:
            logs = Path(d) / "out" / "logs"
            self.assertEqual(runner.log_path(logs, "green", "unit"), logs / "green-unit.log")
            with self.assertRaises(RuntimeError):
                runner.log_path(logs, "green", "../../../escape")


class RedactionTests(unittest.TestCase):
    """The guard log redacts the passwords that curl, custom headers, the AWS CLI, and mysql take."""

    def test_more_secret_shapes_lose_their_value(self):
        secrets = {
            "curl -u alice:s3cretpw https://x": ("s3cretpw", "alice"),
            "curl --user=alice:s3cretpw https://x": ("s3cretpw", "alice"),
            'curl -H "X-Api-Key: k3y-value" https://x': ("k3y-value", "X-Api-Key"),
            "curl -H 'Private-Token: glp-abc123' https://x": ("glp-abc123", "Private-Token"),
            "aws configure set --aws-secret-access-key AKzz9secret": ("AKzz9secret", "--aws-secret-access-key"),
            "aws x --secret-access-key AKzz9secret": ("AKzz9secret", "--secret-access-key"),
            "mysql -u root -pSECRETPW db": ("SECRETPW", "mysql -u root -p"),
        }
        for command, (secret, kept) in secrets.items():
            with self.subTest(command=command):
                out = guard.redact(command)
                self.assertNotIn(secret, out)
                self.assertIn(kept, out)
                self.assertIn("***", out)

    def test_what_is_not_a_secret_stays(self):
        for command in ("gh pr merge 3 --squash", "mysql -u root -p db", "sudo -u www-data ls", "gh pr merge 3 -u"):
            self.assertEqual(guard.redact(command), command)
        self.assertEqual(guard.redact("curl -H 'Authorization: token s3cr3t' x"), "curl -H 'Authorization: token ***' x")


class ApprovalCommitLookupsAreBoundedTests(unittest.TestCase):
    """Looking up the commits that comments name stays bounded, whoever wrote the comment."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "base")
        self.base = git(self.root, "rev-parse", "HEAD")
        Path(self.root, "SPEC.md").write_text("x\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "spec")
        self.spec_commit = git(self.root, "rev-parse", "HEAD")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "impl")
        self.head = git(self.root, "rev-parse", "HEAD")

    def line(self, sha: str) -> str:
        return f"/aidd approve-spec SPEC-1 {'a' * 32} {sha}"

    def count_git(self):
        calls = []
        real = gitutil._git

        def counting(*a, **k):
            calls.append(a[0])
            return real(*a, **k)

        return calls, mock.patch.object(gitutil, "_git", counting)

    def test_only_pool_members_comments_are_looked_up(self):
        spam = [{"user": "mallory", "body": self.line(f"{i:040x}")} for i in range(200)]
        comments = [*spam, {"user": "bob", "body": self.line(self.spec_commit)}]
        calls, patch = self.count_git()
        with patch:
            got = inputs.approval_commits(self.root, self.base, self.head, comments, eligible=inputs.pool_members(["@bob"], {}))
        self.assertEqual(got, {self.spec_commit: {"ancestor": True, "paths": ["SPEC.md"]}})
        self.assertLessEqual(len(calls), 3, calls)

    def test_lookups_are_capped_and_the_newest_are_kept(self):
        comments = [{"user": "bob", "body": self.line(f"{i:040x}")} for i in range(200)]
        comments.append({"user": "bob", "body": self.line(self.spec_commit)})
        calls, patch = self.count_git()
        with patch:
            got = inputs.approval_commits(self.root, self.base, self.head, comments)
        self.assertEqual(len(got), inputs.MAX_APPROVAL_COMMITS)
        self.assertTrue(got[self.spec_commit]["ancestor"])
        self.assertFalse(got[f"{199:040x}"]["ancestor"])
        self.assertLessEqual(len(calls), 3, "missing commits must not spawn git one by one")

    def test_pool_members_resolve_teams_like_the_gate(self):
        members = inputs.pool_members(["@Lead", "@org/sec", "email:A@x.com", "@org/unknown"], {"@org/sec": ["Alice", "bob"]})
        self.assertEqual(members, {"lead", "alice", "bob", "email:a@x.com"})


def _resolves_to(*ips):
    """getaddrinfo answering each call with the next address (the last one repeats): DNS rebinding in a box."""
    answers = list(ips)

    def getaddrinfo(host, port, proto=0, *a, **k):
        ip = answers.pop(0) if len(answers) > 1 else answers[0]
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (ip, port))]

    return getaddrinfo


class ExtendsFetchAddressTests(unittest.TestCase):
    """CGNAT addresses fail the check, and the fetch connects to the address it checked (no DNS rebinding)."""

    def test_non_public_classes_are_refused(self):
        for ip, kind in (
            ("100.64.0.1", "CGNAT"),
            ("100.127.255.254", "CGNAT"),
            ("10.1.2.3", "private"),
            ("192.168.1.1", "private"),
            ("::ffff:10.0.0.1", "private"),
            ("::ffff:127.0.0.1", "loopback"),
            ("fd00::1", "private"),
        ):
            with self.subTest(ip=ip), mock.patch("socket.getaddrinfo", _resolves_to(ip)), self.assertRaises(http.HttpError) as cm:
                inputs.check_public_address("presets.example.com")
            self.assertIn(kind, str(cm.exception))

    def test_a_public_address_is_returned_for_pinning(self):
        with mock.patch("socket.getaddrinfo", _resolves_to("93.184.216.34")):
            self.assertEqual(inputs.check_public_address("presets.example.com"), "93.184.216.34")

    def test_plain_http_is_refused_before_any_lookup(self):
        with mock.patch("socket.getaddrinfo", side_effect=AssertionError("resolved")), self.assertRaises(http.HttpError):
            inputs.fetch_text("http://presets.example.com/aidd.toml")

    def test_the_fetch_connects_to_the_vetted_address_even_if_dns_changes(self):
        connected = []

        def create_connection(address, *a, **k):
            connected.append(address[0])
            raise OSError("stop here")

        with (
            mock.patch.dict(os.environ, {"HTTPS_PROXY": "", "https_proxy": ""}),
            mock.patch("socket.getaddrinfo", _resolves_to("93.184.216.34", "127.0.0.1")),
            mock.patch("socket.create_connection", create_connection),
            mock.patch("time.sleep"),
            self.assertRaises(http.HttpError),
        ):
            inputs.fetch_text("https://presets.example.com/aidd.toml")
        self.assertTrue(connected)
        self.assertEqual(set(connected), {"93.184.216.34"})

    def test_the_extends_chain_stops_at_its_depth_limit_and_says_so(self):
        texts = {f"p{i}.toml": f'aidd_version = "1.0.0"\nprofile = "solo"\nextends = [{{ path = "p{i + 1}.toml" }}]\n' for i in range(10)}
        warns: list[str] = []
        root = 'aidd_version = "1.0.0"\nprofile = "solo"\nextends = [{ path = "p0.toml" }]\n'
        out = inputs.collect_extends(root, read=texts.get, fetch=lambda u: None, warnings=warns)
        self.assertEqual(len(out), inputs.MAX_EXTENDS_DEPTH + 1)
        self.assertTrue(any("deeper than" in w for w in warns), warns)


class HttpLeavesUrllibAloneTests(unittest.TestCase):
    """Importing aidd.http leaves urllib's global opener alone."""

    def test_importing_aidd_does_not_install_a_global_opener(self):
        code = "import urllib.request, sys; sys.path.insert(0, {src!r}); import aidd.http; print(urllib.request._opener is None)"
        from helpers import ROOT

        p = subprocess.run([PY, "-c", code.format(src=str(ROOT / "src"))], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(p.stdout.strip(), "True", p.stderr)


class GuardCoversMcpAndPowerShellTests(unittest.TestCase):
    """Hooks: the matcher missed MCP tools and PowerShell, so an agent could merge through an MCP server."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name).resolve() / "repo"
        make_repo(cls.root, "team")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def hook(self, tool: str, tool_input: dict) -> str:
        out = io.StringIO()
        event = {"tool_name": tool, "cwd": str(self.root), "tool_input": tool_input}
        self.assertEqual(guard.pre_tool_hook(io.StringIO(json.dumps(event)), out), 0)
        return json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"] if out.getvalue() else "allow"

    def test_mcp_tools_that_merge_or_approve_are_denied(self):
        denied = [
            ("mcp__github__merge_pull_request", {"owner": "o", "repo": "r", "pullNumber": 1}),
            ("mcp__plugin_engineering_github__merge_pull_request", {}),
            ("mcp__git__merge", {}),
            ("mcp__gitlab__approve_merge_request", {"iid": 1}),
            ("mcp__gitlab__accept_merge_request", {"iid": 1}),
            ("mcp__github__enable_pull_request_auto_merge", {}),
            ("mcp__github__create_pull_request_review", {"event": "APPROVE", "body": "lgtm"}),
            ("mcp__github__submit_pending_pull_request_review", {"event": "approve"}),
            ("mcp__github__pull_request_review_write", {"method": "create", "event": "APPROVE"}),
            ("mcp__github__create_commit_status", {"state": "success", "context": "aidd/gate"}),
            ("mcp__github__set_commit_status", {"state": "success"}),
            ("mcp__github__add_issue_comment", {"body": "/aidd approve " + "a" * 40}),
        ]
        for tool, tool_input in denied:
            with self.subTest(tool=tool):
                self.assertEqual(self.hook(tool, tool_input), "deny")

    def test_every_other_mcp_tool_is_allowed(self):
        allowed = [
            ("mcp__github__get_pull_request", {"pullNumber": 1}),
            ("mcp__gitlab__list_merge_requests", {}),
            ("mcp__gitlab__get_merge_request", {"iid": 1}),
            ("mcp__github__create_pull_request", {"title": "x"}),
            ("mcp__github__create_pull_request_review", {"event": "COMMENT", "body": "please approve once green"}),
            ("mcp__github__get_commit_status", {}),
            ("mcp__github__add_issue_comment", {"body": "the approval line is in the PR description"}),
            ("mcp__aidd__check_edit", {"path": "src/x.py"}),
        ]
        for tool, tool_input in allowed:
            with self.subTest(tool=tool):
                self.assertEqual(self.hook(tool, tool_input), "allow")

    def test_powershell_gets_the_shell_check(self):
        self.assertEqual(self.hook("PowerShell", {"command": "gh pr merge 3 --squash"}), "deny")
        self.assertEqual(self.hook("PowerShell", {"command": "Get-ChildItem"}), "allow")
        (entry,) = [e for e in self.log() if e["tool"] == "PowerShell"]
        self.assertEqual(entry["command"], "gh pr merge 3 --squash")

    def test_an_mcp_denial_is_logged_without_its_input(self):
        self.hook("mcp__github__merge_pull_request", {"commit_message": "SECRET-BODY"})
        entry = [e for e in self.log() if e["tool"] == "mcp__github__merge_pull_request"][-1]
        self.assertEqual(entry["reason"], "approve_or_merge")
        self.assertNotIn("SECRET-BODY", json.dumps(entry))

    def log(self) -> list[dict]:
        path = self.root / guard.GUARD_LOG
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.is_file() else []

    def test_init_writes_the_new_matcher(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".claude").mkdir()
            old = {
                "hooks": {"PreToolUse": [{"matcher": "Edit|Write|MultiEdit|NotebookEdit|Bash", "hooks": [{"type": "command", "command": repo.HOOK_COMMAND}]}]}
            }
            (root / ".claude" / "settings.json").write_text(json.dumps(old), encoding="utf-8")
            actions: list[str] = []
            repo.install_agent_hooks(root, actions)
            (entry,) = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
            self.assertEqual(entry["matcher"], repo.HOOK_MATCHER)


class PolicyRunsFromTheBaseTests(unittest.TestCase):
    """policy.evaluate_in_base: the Policy script the change edits is not the one that runs."""

    def test_the_base_policy_decides_when_the_head_rewrites_it(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            root.mkdir()
            git(root, "init", "-q", "-b", "main")
            (root / "policy.py").write_text("print('deny base says no')\n", encoding="utf-8")
            git(root, "add", ".")
            git(root, "commit", "-qm", "base policy")
            base = git(root, "rev-parse", "HEAD")
            git(root, "checkout", "-qb", "feature")
            (root / "policy.py").write_text("print('allow')\n", encoding="utf-8")
            git(root, "commit", "-qam", "loosen the policy")
            head = git(root, "rev-parse", "HEAD")
            kw = dict(change_id="1", base_sha=base, head_sha=head, paths=["policy.py"], body="", head_files={})
            got = policy.evaluate_in_base([PY, "policy.py"], repo=str(root), base_ref=base, **kw)
            self.assertEqual(got, {"result": "deny", "detail": "base says no"})
            self.assertEqual(policy.evaluate([PY, "policy.py"], cwd=str(root), **kw)["result"], "allow")  # the checkout is head's
            self.assertNotIn("aidd-base-", git(root, "worktree", "list"))  # the base worktree is removed afterwards


if __name__ == "__main__":
    unittest.main()
