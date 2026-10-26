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


if __name__ == "__main__":
    unittest.main()
