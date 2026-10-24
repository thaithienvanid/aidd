"""`aidd init` at a person's terminal asks instead of hinting (UX audit U13, U14): wire Claude Code too, and commit the
setup as the Day-0 commit. An agent's shell, a pipe, or CI is never asked and gets the written steps, as before."""

from __future__ import annotations

import contextlib
import io
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import git

from aidd.cli import app
from aidd.platforms import local_land
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

    def init(
        self, *answers: str, agent: bool = False, claude_here: bool = False, args: tuple[str, ...] = ("--profile", "solo", "--ci", "none")
    ) -> tuple[int, str, mock.Mock]:
        out = _Terminal()
        env = {k: v for k, v in os.environ.items() if k not in local_land.AGENT_ENV} | ({local_land.AGENT_ENV[0]: "1"} if agent else {})
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(sys, "stdin", _Terminal()),
            mock.patch("builtins.input", side_effect=list(answers)) as asked,
            mock.patch.object(adoption, "installed_harnesses", return_value=["claude-code"] if claude_here else []),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(out),
        ):
            code = app.main(["init", *args, "--no-skill", str(self.root)])
        return code, out.getvalue(), asked

    def test_with_no_platform_a_yes_commits_only_what_init_wrote_on_the_base_branch(self):  # U13
        code, out, asked = self.init("")
        self.assertEqual(code, 0, out)
        self.assertIn("Commit this setup on `main` now", asked.call_args.args[0])
        self.assertEqual(git(self.root, "rev-parse", "--abbrev-ref", "HEAD"), "main")
        self.assertEqual(git(self.root, "log", "-1", "--format=%s"), "chore: adopt aidd")
        committed = git(self.root, "show", "--name-only", "--format=", "HEAD").splitlines()
        self.assertIn(".aidd/config.yaml", committed)
        self.assertNotIn("notes.txt", committed)
        self.assertIn("Committed on main.", out)
        self.assertNotIn("git merge", out)  # no setup branch to land: nothing runs between it and its fast-forward
        self.assertIn("  3. Commit the setup on `main`: init offers it now.", out)
        self.assertNotIn("Assisted-by", out)  # the agent's steps are for an agent's shell

    def test_on_the_day_0_branch_already_it_commits_there(self):
        git(self.root, "switch", "-qc", "chore/adopt-aidd")
        code, out, _ = self.init("")
        self.assertEqual(code, 0, out)
        self.assertEqual(git(self.root, "log", "-1", "--format=%s"), "chore: adopt aidd")
        self.assertIn("git merge --ff-only chore/adopt-aidd", out)

    def test_off_the_base_branch_it_says_so_and_offers_no_commit(self):
        git(self.root, "switch", "-qc", "spec/SPEC-1")
        code, out, asked = self.init()
        self.assertEqual(code, 0, out)
        asked.assert_not_called()
        self.assertIn("note     you are on `spec/SPEC-1`; aidd lands work on `main`", out)
        self.assertIn("Not committed: this is `spec/SPEC-1`, not `main`.", out)
        self.assertEqual(git(self.root, "log", "-1", "--format=%s"), "scaffold")

    def test_on_a_platform_it_commits_on_a_free_setup_branch_and_names_the_pull_request(self):
        git(self.root, "remote", "add", "origin", "https://github.com/acme/shop.git")
        git(self.root, "branch", "chore/adopt-aidd")  # an earlier setup's branch stays as it is
        code, out, asked = self.init("", args=("--profile", "solo", "--ref", "a" * 40))
        self.assertEqual(code, 0, out)
        self.assertIn("Commit this setup on a new branch `chore/adopt-aidd-2` now", asked.call_args.args[0])
        self.assertEqual(git(self.root, "rev-parse", "--abbrev-ref", "HEAD"), "chore/adopt-aidd-2")
        self.assertIn("git push -u origin chore/adopt-aidd-2", out)
        self.assertIn("gh pr create --fill", out)

    def test_a_bare_init_asks_the_profile_and_the_approver(self):
        code, out, asked = self.init("team", "", "n", args=("--ci", "none"))
        self.assertEqual(code, 0, out)
        self.assertIn("Profile (solo, team, org, audited)? [solo]", asked.call_args_list[0].args[0])
        self.assertIn("[email:me@example.com]", asked.call_args_list[1].args[0])
        text = (self.root / ".aidd" / "config.yaml").read_text(encoding="utf-8")
        self.assertIn("profile: team", text)
        self.assertIn("email:me@example.com", text)

    def test_init_again_reads_the_profile_and_approvers_from_the_config_it_keeps(self):
        self.assertEqual(self.init("n", args=("--profile", "team", "--approvers", "@acme/leads", "--ci", "none"))[0], 0)
        code, out, asked = self.init("n", args=("--ci", "none", "--harness", "opencode"))
        self.assertEqual(code, 0, out)
        self.assertNotIn("Profile", " ".join(c.args[0] for c in asked.call_args_list))
        self.assertNotIn("found no test command", out)  # the kept config's tests stand
        self.assertRegex(out, r"wrote    \S*\.opencode/plugins/aidd\.js")
        self.assertIn("Restart OpenCode V2 in this folder", out)
        self.assertEqual(len(re.findall(r"^kept     ", out, re.M)), len(set(re.findall(r"^kept     .*$", out, re.M))))
        self.assertRegex(out, r"kept     \d+ files that exist \(--force replaces them\): \S*\.aidd/config\.yaml, ")

    def test_a_config_deleted_but_committed_is_brought_back_not_replaced(self):
        self.assertEqual(self.init("y")[0], 0)
        (self.root / ".aidd" / "config.yaml").unlink()
        code, out, _ = self.init()
        self.assertEqual(code, 2, out)
        self.assertIn("git restore --source=HEAD --staged --worktree .aidd/config.yaml", out)
        self.assertFalse((self.root / ".aidd" / "config.yaml").exists())

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
