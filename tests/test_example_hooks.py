"""examples/hooks/: a team's own PreToolUse rule next to aidd's guard. The script compiles, answers in Claude Code's
documented shape, and the settings snippet in its README is valid JSON that keeps aidd's guard entry."""

import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, git

from aidd import repo

HOOKS = ROOT / "examples" / "hooks"
SCRIPT = HOOKS / "deny-rm-rf-outside-worktree.py"


@unittest.skipUnless(shutil.which("git"), "git is required")
class ExampleHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / "work"
        self.root.mkdir()
        git(self.root, "init", "-q")
        (self.root / "build").mkdir()

    def answer(self, command: str, tool: str = "Bash", cwd: Path | None = None) -> dict:
        event = {"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": str(cwd or self.root), "tool_input": {"command": command}}
        run = subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps(event), capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout) if run.stdout.strip() else {}

    def test_it_compiles(self):
        py_compile.compile(str(SCRIPT), cfile=os.path.join(self.tmp.name, "x.pyc"), doraise=True)

    def test_denies_rm_rf_outside_the_worktree(self):
        for command in (
            "rm -rf ~/old",
            "rm -rf /",
            "rm -fr ../sibling",
            "rm -r -f /tmp/x",
            "rm --recursive --force /etc",
            "cd build && rm -Rf ../..",
            "sudo rm -rf /var/lib",
            'rm -rf "$HOME"',
            "rm -rf .",
            "FOO=1 rm -rf -- /opt",
        ):
            with self.subTest(command=command):
                out = self.answer(command)["hookSpecificOutput"]
                self.assertEqual((out["hookEventName"], out["permissionDecision"]), ("PreToolUse", "deny"))
                self.assertIn("team rule", out["permissionDecisionReason"])

    def test_lets_everything_else_through(self):
        for command in ("rm -rf build", "rm -rf ./build/cache node_modules", "rm -r ~/old", "rm -f /tmp/x", "ls -la /", "echo rm -rf /", "npm test"):
            with self.subTest(command=command):
                self.assertEqual(self.answer(command), {})
        self.assertEqual(self.answer("rm -rf /", tool="Edit"), {})
        self.assertEqual(self.answer("rm -rf build", cwd=self.root / "build"), {})  # relative to the session's directory

    def test_a_broken_event_allows_quietly(self):
        run = subprocess.run([sys.executable, str(SCRIPT)], input="not json", capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual((run.returncode, run.stdout), (0, ""))
        self.assertIn("skipped", run.stderr)

    def test_the_readme_snippet_keeps_aidds_entry(self):
        text = (HOOKS / "README.md").read_text(encoding="utf-8")
        (block,) = re.findall(r"```json\n(.*?)```", text, re.S)
        entries = json.loads(block)["hooks"]["PreToolUse"]
        self.assertEqual(entries[0]["matcher"], repo.HOOK_MATCHER)
        self.assertEqual(repo.aidd_hook(entries[0]["hooks"][0]["command"]), "pre-edit")
        self.assertIn(SCRIPT.name, entries[1]["hooks"][0]["command"])


if __name__ == "__main__":
    unittest.main()
