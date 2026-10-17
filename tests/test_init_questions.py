"""`aidd init` at a person's terminal asks instead of hinting (UX audit U13, U14): wire Claude Code too, and commit the
setup as the Day-0 commit. An agent's shell, a pipe, or CI is never asked and gets the written steps, as before."""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import git

from aidd.cli import app
from aidd.platforms import local_ship
from aidd.setup import adoption


class _Terminal(io.StringIO):
    def isatty(self):
        return True


class InitQuestionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "me@example.com")
        git(self.root, "config", "user.name", "Me")
        (self.root / "README.md").write_text("# shop\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "scaffold")
        (self.root / "notes.txt").write_text("mine, not init's\n", encoding="utf-8")  # dirty before init: never committed

    def init(self, *answers: str, agent: bool = False, claude_here: bool = False) -> tuple[int, str, mock.Mock]:
        out = _Terminal()
        env = {k: v for k, v in os.environ.items() if k not in local_ship.AGENT_ENV} | ({local_ship.AGENT_ENV[0]: "1"} if agent else {})
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(sys, "stdin", _Terminal()),
            mock.patch("builtins.input", side_effect=list(answers)) as asked,
            mock.patch.object(adoption, "installed_harnesses", return_value=["claude-code"] if claude_here else []),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(out),
        ):
            code = app.main(["init", "--profile", "solo", "--ci", "none", "--no-skill", str(self.root)])
        return code, out.getvalue(), asked

    def test_a_yes_commits_only_what_init_wrote_on_its_own_branch(self):  # U13
        code, out, asked = self.init("")
        self.assertEqual(code, 0, out)
        self.assertIn("Commit this setup now", asked.call_args.args[0])
        self.assertEqual(git(self.root, "rev-parse", "--abbrev-ref", "HEAD"), "chore/adopt-aidd")
        self.assertEqual(git(self.root, "log", "-1", "--format=%s"), "chore: adopt aidd")
        committed = git(self.root, "show", "--name-only", "--format=", "HEAD").splitlines()
        self.assertIn(".aidd/config.yaml", committed)
        self.assertNotIn("notes.txt", committed)
        self.assertIn("git merge --ff-only chore/adopt-aidd", out)

    def test_on_the_day_0_branch_already_it_commits_there(self):
        git(self.root, "switch", "-qc", "chore/adopt-aidd")
        code, out, _ = self.init("")
        self.assertEqual(code, 0, out)
        self.assertEqual(git(self.root, "log", "-1", "--format=%s"), "chore: adopt aidd")
        self.assertIn("git merge --ff-only chore/adopt-aidd", out)

    def test_a_no_leaves_the_setup_uncommitted(self):
        code, out, _ = self.init("n")
        self.assertEqual(code, 0, out)
        self.assertEqual(git(self.root, "rev-parse", "--abbrev-ref", "HEAD"), "main")
        self.assertEqual(git(self.root, "log", "-1", "--format=%s"), "scaffold")

    def test_an_agents_shell_is_never_asked(self):
        code, out, asked = self.init(agent=True, claude_here=True)
        self.assertEqual(code, 0, out)
        asked.assert_not_called()
        self.assertEqual(git(self.root, "log", "-1", "--format=%s"), "scaffold")
        self.assertIn("hint     this machine has Claude Code", out)

    def test_claude_code_on_this_machine_is_wired_on_a_yes(self):  # U14
        code, out, asked = self.init("y", "n", claude_here=True)
        self.assertEqual(code, 0, out)
        self.assertIn("Wire it in this repository too", asked.call_args_list[0].args[0])
        self.assertTrue((self.root / ".claude").is_dir(), out)
        self.assertNotIn("hint     this machine has Claude Code", out)

    def test_claude_code_stays_unwired_on_a_no(self):
        code, out, _ = self.init("n", "n", claude_here=True)
        self.assertEqual(code, 0, out)
        self.assertFalse((self.root / ".claude").exists())


if __name__ == "__main__":
    unittest.main()
