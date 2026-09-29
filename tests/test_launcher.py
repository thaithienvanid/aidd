"""The launcher the generated hooks and MCP config use, and `aidd doctor` actually running them.

aidd is pre-release and installed from a checkout, so a bare `aidd` in `.claude/settings.json` often names nothing:
init resolves the launcher when it runs, and doctor starts both once and fails when either cannot run.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import git

from aidd import repo


class LauncherTests(unittest.TestCase):
    def test_aidd_on_path_is_used_as_is(self):
        with mock.patch.object(repo.shutil, "which", return_value="/usr/local/bin/aidd"):
            self.assertEqual(repo.launcher(), (["aidd"], {}))
            self.assertEqual(repo.hook_command("pre-edit"), repo.HOOK_COMMAND)
            self.assertEqual(repo.hook_command("stop"), repo.SESSION_HOOKS["Stop"])
            self.assertEqual(repo.mcp_server(), {"command": "aidd", "args": ["mcp"]})

    def test_otherwise_this_interpreter_with_the_source_on_pythonpath(self):
        src = str(Path(repo.__file__).resolve().parent.parent)
        with mock.patch.object(repo.shutil, "which", return_value=None), mock.patch.object(repo, "_on_default_path", return_value=False):
            argv, env = repo.launcher()
            self.assertEqual(argv, [sys.executable, "-m", "aidd"])
            self.assertEqual(env, {"PYTHONPATH": src})
            self.assertTrue(
                repo.hook_command("pre-edit").endswith(f"{sys.executable} -m aidd hook pre-edit".replace(sys.executable, repo.shlex.quote(sys.executable)))
            )
            self.assertEqual(repo.aidd_hook(repo.hook_command("session-start")), "session-start")
            self.assertEqual(repo.mcp_server(), {"command": sys.executable, "args": ["-m", "aidd", "mcp"], "env": {"PYTHONPATH": src}})
        with mock.patch.object(repo.shutil, "which", return_value=None), mock.patch.object(repo, "_on_default_path", return_value=True):
            self.assertEqual(repo.launcher(), ([sys.executable, "-m", "aidd"], {}))  # installed in site-packages: no PYTHONPATH

    def test_every_launcher_form_is_recognised_as_ours(self):
        for command in ("aidd hook pre-edit", "PYTHONPATH=/x /usr/bin/python3 -m aidd hook pre-edit", "'/a b/python' -m aidd hook pre-edit"):
            self.assertEqual(repo.aidd_hook(command), "pre-edit", command)
        self.assertEqual(repo.aidd_hook("aidd hook stop || true"), "stop")
        self.assertIsNone(repo.aidd_hook("my-aidd hook pre-edit-x"))
        self.assertIsNone(repo.aidd_hook(None))


@unittest.skipUnless(shutil.which("git"), "git is required")
class DoctorRunsTheWiringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q")
        repo.init(self.root, profile="team", ci="none", links=[], approvers=["@lead"], harnesses=["claude-code"])
        self.settings = self.root / ".claude" / "settings.json"

    def tearDown(self):
        self.tmp.cleanup()

    def claude_lines(self, execute=True):
        return [(lvl, m) for lvl, m in repo.doctor(self.root, execute=execute) if m.startswith("Claude Code: the edit-time hook")]

    def set_pre_edit(self, command):
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        for e in data["hooks"]["PreToolUse"]:
            for h in e["hooks"]:
                if repo.aidd_hook(h["command"]) == "pre-edit":
                    h["command"] = command
        self.settings.write_text(json.dumps(data), encoding="utf-8")

    def test_the_wiring_init_writes_runs(self):
        self.assertEqual(self.claude_lines(), [("ok", "Claude Code: the edit-time hook and the MCP server are wired, and both start")])

    def test_a_hook_whose_launcher_is_missing_fails(self):
        self.set_pre_edit("/nonexistent/bin/aidd hook pre-edit")
        [(level, message)] = [x for x in repo.doctor(self.root, execute=False) if x[1].startswith("Claude Code: ") and "edit-time hook `" in x[1]]
        self.assertEqual(level, "fail")
        self.assertIn("not found here", message)
        self.assertIn("aidd init --agent-hooks", message)

    def test_a_hook_that_resolves_but_cannot_run_fails_when_executed(self):
        self.set_pre_edit(f"PYTHONPATH={self.tmp.name}/nowhere {repo.shlex.quote(sys.executable)} -m aidd hook pre-edit")
        found = [x for x in repo.doctor(self.root, execute=True) if x[1].startswith("Claude Code: ") and "does not run" in x[1]]
        self.assertEqual([lvl for lvl, _ in found], ["fail"], found)
        self.assertIn("No module named aidd", found[0][1])
        self.assertNotIn(("ok", "Claude Code: the edit-time hook and the MCP server are wired, and both start"), repo.doctor(self.root, execute=True))

    def test_doctor_never_runs_a_launcher_the_repository_supplies(self):
        evil = self.root / "bin" / "aidd"
        evil.parent.mkdir()
        marker = Path(self.tmp.name) / "ran"
        evil.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
        evil.chmod(0o755)
        self.set_pre_edit(f"{evil} hook pre-edit")
        found = [m for lvl, m in repo.doctor(self.root, execute=True) if lvl == "fail" and "not run: " in m]
        self.assertTrue(found, repo.doctor(self.root, execute=True))
        self.assertFalse(marker.exists())
        self.assertIn("inside the repository", repo.run_hook_probe(self.root, f"{evil} hook pre-edit") or "")
        self.assertIn("not an aidd launcher", repo.run_hook_probe(self.root, "sh -c 'touch x' hook pre-edit") or "")

    def test_an_mcp_command_that_does_not_resolve_fails(self):
        mcp = self.root / ".mcp.json"
        mcp.write_text(json.dumps({"mcpServers": {"aidd": {"command": "no-such-aidd-launcher", "args": ["mcp"]}}}), encoding="utf-8")
        found = [(lvl, m) for lvl, m in repo.doctor(self.root) if "MCP server's command" in m]
        self.assertEqual([lvl for lvl, _ in found], ["fail"])
        # init repairs an aidd entry whose launcher does not resolve here, and keeps one that does.
        actions: list[str] = []
        repo.install_agent_hooks(self.root, actions)
        self.assertEqual(json.loads(mcp.read_text(encoding="utf-8"))["mcpServers"]["aidd"], repo.mcp_server())
        self.assertTrue(any("its launcher did not resolve here" in a for a in actions), actions)
        self.assertIsNone(repo.run_mcp_probe(self.root, repo.mcp_server()))

    def test_init_repairs_a_hook_whose_launcher_does_not_resolve(self):
        self.set_pre_edit("/nonexistent/bin/aidd hook pre-edit")
        actions: list[str] = []
        repo.install_agent_hooks(self.root, actions)
        # Read as JSON, not as text: a Windows path's backslashes are escaped in the file.
        hooks = json.loads(self.settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        self.assertIn(repo.hook_command("pre-edit"), [h["command"] for e in hooks for h in e["hooks"]])
        self.assertEqual(self.claude_lines(), [("ok", "Claude Code: the edit-time hook and the MCP server are wired, and both start")])


if __name__ == "__main__":
    unittest.main()
