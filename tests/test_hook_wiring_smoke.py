"""The guard hook as it is wired, end to end: the command `aidd init` writes into `.claude/settings.json`, and the
plugin's own hooks/hooks.json, each run through a shell with AIDD_HOOK_FAIL_CLOSED=1.

The hook is advisory: when it cannot start (a launcher naming the wrong source folder, a loader whose import moved), it
allows by default, and nothing fails. Fail-closed turns that into exit 2, so a broken launcher shows here as a failure
instead of as a guard that silently allows everything. Each launcher must deny an agent's merge and allow an ordinary
edit, and init's launcher must name the source folder that holds this very aidd package: a launcher computed from a
module's own place (`Path(__file__).parent.parent`) goes wrong when that module moves into a package.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, aidd_subprocess, git

from aidd.setup import hook_wiring

MERGE = {"tool_name": "Bash", "tool_input": {"command": "gh pr merge 1"}}
EDIT = {"tool_name": "Edit", "tool_input": {"file_path": "app.py"}}


@unittest.skipIf(os.name == "nt" or not shutil.which("git") or not shutil.which("sh"), "the hook commands run under a POSIX shell")
class HookWiringSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        base = Path(cls._tmp.name).resolve()
        cls.root = base / "repo"
        cls.root.mkdir()
        git(cls.root, "init", "-q")
        init = aidd_subprocess("init", "--profile", "solo", "--ci", "none", "--approvers", "email:dev@example.com", "--harness", "claude-code", cwd=cls.root)
        if init.returncode != 0:
            raise AssertionError(f"aidd init failed: {init.stdout}{init.stderr}")
        cls.settings = json.loads((cls.root / ".claude" / "settings.json").read_text(encoding="utf-8"))
        # A PATH with only what the hooks need, outside the repository: python3 (this interpreter), env, and git.
        cls.bin = base / "bin"
        cls.bin.mkdir()
        for name, target in (("python3", sys.executable), ("env", shutil.which("env")), ("git", shutil.which("git"))):
            (cls.bin / name).symlink_to(target or f"/usr/bin/{name}")

    def init_commands(self, hook: str) -> list[str]:
        found = [
            h["command"] for entries in self.settings["hooks"].values() for e in entries for h in e["hooks"] if hook_wiring.aidd_hook(h["command"]) == hook
        ]
        self.assertTrue(found, f"init wrote no {hook} hook")
        return found

    def run_sh(self, command: str, event: dict | None, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [shutil.which("sh") or "/bin/sh", "-c", command],
            input=json.dumps({**event, "cwd": str(self.root)}) if event is not None else "{}",
            cwd=self.root,
            env={"PATH": str(self.bin), "HOME": os.environ["HOME"], "AIDD_HOOK_FAIL_CLOSED": "1", **env},  # init wrote the user launcher there
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )

    def assert_guards(self, command: str, what: str, **env: str) -> None:
        denied = self.run_sh(command, MERGE, **env)
        self.assertEqual(denied.returncode, 0, f"{what}: the hook did not run: {denied.stderr}")
        self.assertEqual(json.loads(denied.stdout)["hookSpecificOutput"]["permissionDecision"], "deny", f"{what}: {denied.stdout}")
        allowed = self.run_sh(command, EDIT, **env)
        self.assertEqual(allowed.returncode, 0, f"{what}: the hook did not run: {allowed.stderr}")
        self.assertNotIn('"deny"', allowed.stdout, what)

    def test_init_names_the_source_folder_of_this_aidd(self):
        (command,) = self.init_commands("pre-tool")
        self.assertTrue(command.startswith(f"{hook_wiring.HOOK_LAUNCHER} hook pre-tool"), command)  # the user launcher holds the rest
        words, why = hook_wiring.read_user_launcher()
        self.assertIsNotNone(words, why)
        assert words is not None
        if words[1:4] != ["-I", "-c", hook_wiring.LOADER]:
            self.skipTest("aidd is installed in this interpreter's site-packages, so init writes `-m aidd`")
        package = Path(words[4]) / "aidd" / "__init__.py"
        self.assertTrue(package.is_file() and package.samefile(ROOT / "src" / "aidd" / "__init__.py"), f"{words[4]} does not hold this aidd")

    def test_the_guard_hook_init_writes_denies_a_merge_and_allows_an_edit(self):
        (command,) = self.init_commands("pre-tool")
        self.assert_guards(command, "init's pre-tool hook")

    def test_the_session_hooks_init_writes_run(self):
        # They end in `|| true`, so a session never stops on them: a launcher that cannot start shows only on stderr.
        for hook in ("session-start", "stop"):
            for command in self.init_commands(hook):
                run = self.run_sh(command, None)
                self.assertEqual((run.returncode, run.stderr), (0, ""), hook)

    def test_the_plugin_guard_hook_denies_a_merge_and_allows_an_edit(self):
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        self.assert_guards(
            hooks["PreToolUse"][0]["hooks"][0]["command"], "the plugin's pre-tool hook", CLAUDE_PLUGIN_ROOT=str(ROOT), CLAUDE_PROJECT_DIR=str(self.root)
        )

    def test_doctor_runs_the_wiring_init_wrote(self):
        run = aidd_subprocess("doctor", cwd=self.root)
        self.assertIn("the guard hook and the MCP server are wired, and both start", run.stdout, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
