"""The user launcher (~/.aidd/bin/aidd): `aidd init` writes this machine's way to start aidd there, outside every
repository, so the hook commands and the MCP entry it commits name no machine's path and are the same for every
contributor. Where the launcher cannot run, the guard says so instead of failing silently, and doctor refuses a
launcher that `aidd init` did not write or that another user could change.
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import git, make_repo

from aidd.guard import pre_tool
from aidd.setup import adoption, doctor_checks, doctor_probes, hook_wiring, uninstalling

POSIX = os.name != "nt" and shutil.which("sh") is not None and shutil.which("git") is not None
EDIT_CONFIG = {"tool_name": "Edit", "tool_input": {"file_path": ".aidd/config.yaml"}}


def claude_files(root: Path) -> str:
    return (root / ".claude" / "settings.json").read_text(encoding="utf-8") + (root / ".mcp.json").read_text(encoding="utf-8")


@unittest.skipUnless(POSIX, "the user launcher is a POSIX script; on Windows init still writes this machine's launcher")
class UserLauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q")
        self.home = Path(os.environ["HOME"])
        self.addCleanup(shutil.rmtree, self.home / ".aidd", True)
        self.init_actions = adoption.init(
            self.root, adoption.InitOptions(profile="solo", ci="none", links=[], approvers=["email:dev@example.com"], harnesses=["claude-code"])
        )
        self.launcher = hook_wiring.user_launcher_path()

    def guard(self) -> str:
        data = json.loads((self.root / ".claude" / "settings.json").read_text(encoding="utf-8"))
        (command,) = [h["command"] for e in data["hooks"]["PreToolUse"] for h in e["hooks"] if hook_wiring.aidd_hook(h["command"]) == "pre-tool"]
        return command

    def session_start(self) -> str:
        data = json.loads((self.root / ".claude" / "settings.json").read_text(encoding="utf-8"))
        (command,) = [h["command"] for e in data["hooks"]["SessionStart"] for h in e["hooks"]]
        return command

    def run_sh(self, command: str, home: Path, event: dict | None = None, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["/bin/sh", "-c", command],
            input=json.dumps({**(event or {}), "cwd": str(self.root)}),
            cwd=self.root,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home), **env},
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )

    def doctor_claude(self) -> list[tuple[str, str]]:
        return [(lvl, m) for lvl, m in doctor_checks.doctor(self.root, execute=True) if m.startswith("Claude Code: ")]

    def test_init_writes_the_launcher_and_commits_no_machine_path(self):
        argv, why = hook_wiring.read_user_launcher()
        self.assertIsNotNone(argv, why)
        self.assertEqual(argv, hook_wiring.launcher()[0])
        self.assertTrue(os.access(self.launcher, os.X_OK))
        text = claude_files(self.root)
        for machine in (str(self.home), sys.executable, os.path.realpath(sys.executable)):
            self.assertNotIn(machine, text)
        self.assertTrue(self.guard().startswith(f"{hook_wiring.HOOK_LAUNCHER} hook pre-tool || "))
        self.assertEqual(
            json.loads((self.root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["aidd"], {"command": "${HOME}/.aidd/bin/aidd", "args": ["mcp"]}
        )
        self.assertTrue(any(a.startswith("wrote    ~/.aidd/bin/aidd") for a in self.init_actions), self.init_actions)

    def test_every_contributor_gets_the_same_files(self):
        before = claude_files(self.root)
        other = Path(self.tmp.name) / "other-home"
        other.mkdir()
        with mock.patch.dict(os.environ, {"HOME": str(other)}):
            actions: list[str] = []
            hook_wiring.install_claude_hooks(self.root, actions)
            self.assertTrue((other / ".aidd" / "bin" / "aidd").is_file())
        self.assertEqual(claude_files(self.root), before)
        self.assertTrue(any(a.startswith("kept") and a.endswith("settings.json (the aidd hook is there)") for a in actions), actions)

    def test_the_guard_runs_through_the_launcher(self):
        r = self.run_sh(self.guard(), self.home, EDIT_CONFIG)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_without_the_launcher_the_guard_says_so_and_blocks_only_when_fail_closed(self):
        empty = Path(self.tmp.name) / "new-contributor"
        empty.mkdir()
        r = self.run_sh(self.guard(), empty, EDIT_CONFIG)
        self.assertEqual(r.returncode, 1)  # Claude Code shows a hook error and goes on: the guard allows when it cannot run
        self.assertIn("aidd: the guard could not run on this machine. Install aidd", r.stderr)
        self.assertIn("then run aidd init --claude-hooks", r.stderr)
        self.assertEqual(self.run_sh(self.guard(), empty, EDIT_CONFIG, AIDD_HOOK_FAIL_CLOSED="1").returncode, 2)  # a block

    def test_without_the_launcher_session_start_tells_the_agent(self):
        empty = Path(self.tmp.name) / "new-contributor"
        empty.mkdir()
        r = self.run_sh(self.session_start(), empty)
        self.assertEqual(r.returncode, 0)
        self.assertIn("so the guard is off. Run aidd init --claude-hooks", r.stdout)

    def test_doctor_names_the_missing_launcher_and_the_fix(self):
        self.launcher.unlink()
        [(level, message)] = [x for x in self.doctor_claude() if "guard hook" in x[1]]
        self.assertEqual(level, "fail")
        self.assertIn("~/.aidd/bin/aidd is missing on this machine", message)
        self.assertIn("`aidd init --claude-hooks` repairs it on this machine", message)
        self.assertIn("the MCP server", message)

    def test_doctor_refuses_a_launcher_init_did_not_write(self):
        good = self.launcher.read_text(encoding="utf-8")
        cases = {
            "changed": lambda: self.launcher.write_text(good.replace("exec ", "touch /tmp/x; exec "), encoding="utf-8"),
            "not isolated": lambda: self.launcher.write_text(hook_wiring.launcher_script([sys.executable, "-m", "aidd"]), encoding="utf-8"),
            "others can write": lambda: self.launcher.chmod(0o777),
            "its folder others can write": lambda: self.launcher.parent.chmod(0o777),
        }
        for label, spoil in cases.items():
            with self.subTest(label):
                spoil()
                self.assertIsNone(hook_wiring.read_user_launcher()[0])
                self.assertIn("fail", [lvl for lvl, _ in self.doctor_claude()])
                self.launcher.parent.chmod(0o755)
                self.launcher.write_text(good, encoding="utf-8")
                self.launcher.chmod(0o755)
        self.assertIsNotNone(hook_wiring.read_user_launcher()[0])

    def test_doctor_fails_when_the_settings_move_home(self):
        # Claude Code passes a settings `env` to the hooks: a HOME there would name another launcher than doctor checks.
        self.assertNotIn("fail", [lvl for lvl, _ in self.doctor_claude()])
        local = self.root / ".claude" / "settings.local.json"
        local.write_text(json.dumps({"env": {"HOME": str(self.root)}}), encoding="utf-8")
        failed = [m for lvl, m in self.doctor_claude() if lvl == "fail"]
        self.assertEqual(len(failed), 1, failed)
        self.assertIn("settings.local.json sets HOME in its `env`", failed[0])
        self.assertNotIn("ok", [lvl for lvl, m in self.doctor_claude() if "guard hook and the MCP server are wired" in m])

    def test_a_linked_launcher_is_refused(self):
        target = Path(self.tmp.name) / "elsewhere"
        target.write_text(self.launcher.read_text(encoding="utf-8"), encoding="utf-8")
        self.launcher.unlink()
        self.launcher.symlink_to(target)
        self.assertEqual(hook_wiring.read_user_launcher()[1], "~/.aidd/bin/aidd is not a file")

    def test_a_launcher_into_the_repository_is_never_written_nor_run(self):
        good = self.launcher.read_text(encoding="utf-8")
        inside = ([str(self.root / ".venv" / "bin" / "python"), "-I", "-m", "aidd"], {})
        actions: list[str] = []
        hook_wiring.install_user_launcher(self.root, inside, actions)
        self.assertEqual(self.launcher.read_text(encoding="utf-8"), good)
        self.assertIn("is inside the repository", actions[0])
        # Written by hand, doctor refuses to run it in that repository.
        self.launcher.write_text(hook_wiring.launcher_script(inside[0]), encoding="utf-8")
        self.assertIn("is inside the repository", doctor_probes.run_hook_probe(self.root, self.guard()) or "")

    def test_init_moves_an_older_machine_path_command_to_the_launcher(self):
        settings = self.root / ".claude" / "settings.json"
        data = json.loads(settings.read_text(encoding="utf-8"))
        old = hook_wiring._shell_launcher(hook_wiring.launcher()[0], {}) + " hook pre-tool"
        for e in data["hooks"]["PreToolUse"]:
            for h in e["hooks"]:
                h["command"] = old
        mcp = self.root / ".mcp.json"
        argv = hook_wiring.launcher()[0]
        mcp.write_text(json.dumps({"mcpServers": {"aidd": {"command": argv[0], "args": [*argv[1:], "mcp"]}}}), encoding="utf-8")
        settings.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn(hook_wiring.NOT_INIT_WRITTEN, doctor_probes.run_hook_probe(self.root, old) or "")
        actions: list[str] = []
        hook_wiring.install_claude_hooks(self.root, actions)
        self.assertTrue(self.guard().startswith(hook_wiring.HOOK_LAUNCHER), self.guard())
        self.assertTrue(any("now start aidd through ~/.aidd/bin/aidd" in a for a in actions), actions)
        self.assertEqual(json.loads(mcp.read_text(encoding="utf-8"))["mcpServers"]["aidd"], hook_wiring.mcp_server())
        self.assertNotIn(sys.executable, claude_files(self.root))

    def test_uninstall_keeps_the_launcher_every_repository_shares(self):
        actions = uninstalling.uninstall(self.root, yes=True)
        self.assertTrue(self.launcher.is_file())
        self.assertTrue(any(a.startswith("kept     ~/.aidd/bin/aidd") for a in actions), actions)


@unittest.skipIf(os.name == "nt", "the launcher is an sh script")
class TwoInstallsTests(unittest.TestCase):
    """An agent's shell runs the `aidd` on PATH and the hooks run the launcher: doctor says when they are two installs."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.bin = Path(tmp.name) / "bin"
        self.bin.mkdir()
        self.other = Path(tmp.name) / "other-python"
        self.other.write_text("#!/bin/sh\n", encoding="utf-8")
        self.other.chmod(0o755)

    def problem(self, python: str) -> str | None:
        script = self.bin / "aidd"
        script.write_text(f"#!{python}\nimport sys\n", encoding="utf-8")
        script.chmod(0o755)
        launcher = ([sys.executable, "-I", "-m", "aidd"], None)
        with mock.patch.object(hook_wiring, "read_user_launcher", return_value=launcher), mock.patch.dict(os.environ, {"PATH": str(self.bin)}):
            return doctor_probes.path_aidd_problem()

    def test_one_install_is_quiet_and_two_are_named(self):
        self.assertIsNone(self.problem(sys.executable))
        two = self.problem(str(self.other)) or ""
        self.assertIn("two releases", two)
        self.assertIn("`aidd init`", two)


class GuardDeadlineTests(unittest.TestCase):
    def setUp(self):
        # The guard fails closed in the repository it runs in, so it runs in one that adopted aidd, wherever the tests run.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_repo(Path(tmp.name).resolve() / "repo", "team", enforce=False)

    def slow_guard(self, **env: str) -> tuple[int, str]:
        out = io.StringIO()
        with (
            contextlib.chdir(self.root),
            mock.patch.object(pre_tool, "_pre_tool", side_effect=lambda stdin, stdout: time.sleep(5) or 0),
            mock.patch.dict(os.environ, env),
        ):
            code = pre_tool.pre_tool_hook(io.StringIO("{}"), out, deadline_seconds=0.2)
        return code, out.getvalue()

    @unittest.skipUnless(hasattr(__import__("signal"), "setitimer"), "a POSIX timer")
    def test_a_guard_past_its_deadline_decides_before_claude_codes_timeout(self):
        # Past the hook's timeout Claude Code lets the call through; the guard's own deadline keeps fail-closed a block.
        self.assertLess(pre_tool.DEADLINE_SECONDS, 20)
        start = time.monotonic()
        self.assertEqual(self.slow_guard(), (0, ""))  # it allows by default, as on any failure of its own
        self.assertLess(time.monotonic() - start, 3)
        code, out = self.slow_guard(AIDD_HOOK_FAIL_CLOSED="1")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("within 0.2 seconds", out)


if __name__ == "__main__":
    unittest.main()
