"""aidd's own launcher and installed code are never an agent's to write: every repository's hooks start from
`~/.aidd/bin/aidd`, so a program that wraps it reads, or switches off, the guard of every repository at once."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import git, make_repo

from aidd.guard import command_check, delegation

MAIN = {"tool_name": "Bash"}
ROLE = {"tool_name": "Bash", "agent_type": "aidd-team:developer"}


@unittest.skipUnless(shutil.which("git"), "git is required")
class LauncherWritesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = make_repo(Path(cls.tmp.name).resolve() / "repo")
        git(cls.root, "commit", "-q", "--allow-empty", "-m", "c1")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def decide(self, command: str, event: dict) -> str:
        return command_check.check_command(str(self.root), str(self.root), command, event)[0]

    def test_a_shell_write_to_the_launcher_is_denied_for_every_session(self):
        for command in (
            "echo x > ~/.aidd/bin/aidd",
            "echo x > $HOME/.aidd/bin/aidd",
            "tee ~/.aidd/bin/aidd < x",
            "cp x ~/.aidd/bin/",
            "cd ~/.aidd/bin && printf x > aidd",
            "echo x > ~/.aidd/notes",
            "rm -rf ~/.aidd",
            "mv ~/.aidd ~/old",
        ):
            for event in (MAIN, ROLE):
                with self.subTest(command=command, role=bool(event.get("agent_type"))):
                    self.assertEqual(self.decide(command, event), "deny")

    def test_reading_it_and_writing_elsewhere_in_the_home_folder_stay_allowed(self):
        for command in ("cat ~/.aidd/bin/aidd", "echo x > ~/notes.txt", "ls ~/.aidd"):
            with self.subTest(command=command):
                self.assertEqual(self.decide(command, MAIN), "allow")

    def test_an_installed_package_is_held_and_a_source_checkout_is_not(self):
        home = os.path.expanduser("~")
        self.assertTrue(delegation._aidd_install(os.path.join(home, ".aidd", "bin", "aidd")))
        with mock.patch.object(delegation, "_PACKAGE", "/x/lib/python3.14/site-packages/aidd"):
            self.assertTrue(delegation._aidd_install("/x/lib/python3.14/site-packages/aidd/guard/pre_tool.py"))
        # This test runs from a source checkout, whose code is the repository's own work.
        self.assertFalse(delegation._aidd_install(os.path.join(os.path.dirname(delegation.__file__), "pre_tool.py")))

    def test_claude_codes_installed_plugins_are_held_and_each_plugins_data_is_not(self):
        """aidd's hooks, its MCP server, and the aidd-cli plugin's `aidd` run from Claude Code's plugin cache, and its
        records say which copy loads."""
        for command in (
            "echo x > ~/.claude/plugins/cache/aidd/aidd-cli/0123456789ab/bin/aidd",
            "sed -i '' s/a/b/ ~/.claude/plugins/cache/aidd/aidd/0123456789ab/src/aidd/guard/pre_tool.py",
            "echo {} > ~/.claude/plugins/installed_plugins.json",
            "cp x ~/.claude/plugins/marketplaces/aidd/scripts/aidd",
            "rm -rf ~/.claude/plugins",
            "mv ~/.claude ~/old-claude",
        ):
            for event in (MAIN, ROLE):
                with self.subTest(command=command, role=bool(event.get("agent_type"))):
                    self.assertEqual(self.decide(command, event), "deny")
        for command in ("echo x > ~/.claude/plugins/data/some-plugin/state.json", "cat ~/.claude/plugins/installed_plugins.json"):
            with self.subTest(command=command):
                self.assertEqual(self.decide(command, MAIN), "allow")

    def test_a_moved_plugins_folder_is_held_where_it_moved(self):
        with tempfile.TemporaryDirectory() as tmp:
            moved = Path(tmp).resolve() / "plugins"
            with mock.patch.dict(os.environ, {"CLAUDE_CODE_PLUGIN_CACHE_DIR": str(moved)}):
                self.assertIsNotNone(delegation.harness_record(moved / "cache" / "aidd" / "aidd-cli" / "x" / "bin" / "aidd"))
                self.assertIsNone(delegation.harness_record(moved / "data" / "aidd" / "state.json"))
                self.assertIsNone(delegation.harness_record(Path(tmp) / "elsewhere.txt"))
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": tmp}):
                self.assertIsNotNone(delegation.harness_record(Path(tmp) / "plugins" / "known_marketplaces.json"))
            seeds = [Path(tmp).resolve() / "seed-a", Path(tmp).resolve() / "seed-b"]
            with mock.patch.dict(os.environ, {"CLAUDE_CODE_PLUGIN_SEED_DIR": os.pathsep.join(map(str, seeds))}):
                for seed in seeds:  # a seed folder is held whole, its data/ too
                    self.assertIsNotNone(delegation.harness_record(seed / "cache" / "aidd" / "aidd" / "x" / "hooks" / "hooks.json"))
                    self.assertIsNotNone(delegation.harness_record(seed / "data" / "aidd" / "state.json"))


if __name__ == "__main__":
    unittest.main()
