"""Claude Code's user folder is `CLAUDE_CONFIG_DIR` when it is set, else `~/.claude`, and every place that reads a file from it
reads that folder: the doctor's check that hooks are off in the person's own settings, and the hint that Claude Code is on
the machine."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import aidd_here, git

from aidd import config
from aidd.setup import adoption, delegation_wiring


class ClaudeUserFolder(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.root, self.home, self.custom = base / "repo", base / "home", base / "custom-claude"
        for folder in (self.root, self.home, self.custom):
            folder.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.name", "Maya Lee")
        git(self.root, "config", "user.email", "maya@users.noreply.github.com")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "start")
        done = aidd_here("init", ".", "--profile", "solo", "--ci", "none", "--harness", "claude-code", "--delegate", cwd=self.root)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.cfg = config.load_file(config.CONFIG_PATH, str(self.root))

    def hooks_off(self) -> list[str]:
        return [m for level, m in delegation_wiring.doctor_lines(self.root, self.cfg) if level == "warning" and "disableAllHooks" in m]

    def test_the_hooks_off_warning_reads_the_user_settings_where_claude_code_keeps_them(self):
        """Table: where the user settings sit (the default folder or `CLAUDE_CONFIG_DIR`), and whether they switch hooks off."""
        off = json.dumps({"disableAllHooks": True})
        for name, env, put, warns in (
            ("default folder, hooks off", {}, lambda: (self.home / ".claude").mkdir() or (self.home / ".claude" / "settings.json").write_text(off), True),
            ("custom folder, hooks off", {"CLAUDE_CONFIG_DIR": "custom"}, lambda: (self.custom / "settings.json").write_text(off), True),
            ("custom folder, hooks on", {"CLAUDE_CONFIG_DIR": "custom"}, lambda: (self.custom / "settings.json").write_text("{}"), False),
            (
                "custom folder set, the default one says off",
                {"CLAUDE_CONFIG_DIR": "custom"},
                lambda: (self.home / ".claude").mkdir() or (self.home / ".claude" / "settings.json").write_text(off),
                False,
            ),
        ):
            with self.subTest(name):
                for stale in (self.home / ".claude", self.custom / "settings.json"):
                    if stale.is_file():
                        stale.unlink()
                    elif stale.is_dir():
                        for child in stale.iterdir():
                            child.unlink()
                        stale.rmdir()
                put()
                env = {k: str(self.custom) for k in env}
                with mock.patch.dict(os.environ, {"HOME": str(self.home), **env}), mock.patch.object(Path, "home", return_value=self.home):
                    if not env:
                        os.environ.pop("CLAUDE_CONFIG_DIR", None)
                    found = self.hooks_off()
                self.assertEqual(len(found), 1 if warns else 0, found)
                if warns:
                    self.assertIn(str(self.custom / "settings.json" if env else self.home / ".claude" / "settings.json"), found[0])

    def test_claude_code_in_a_custom_folder_counts_as_on_the_machine(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.custom)}):
            found = adoption.installed_harnesses(home=self.home, path="")
        self.assertIn("claude-code", found)
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.home / "no-such-folder")}):
            self.assertNotIn("claude-code", adoption.installed_harnesses(home=self.home, path=""))


if __name__ == "__main__":
    unittest.main()
