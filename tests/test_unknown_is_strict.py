"""An answer of `allow` from `aidd risk` comes from a rule, or says that no rule matched: an unknown is never read as `allow`.

The invariants, each held by a table over its input space:

1. A push whose branch aidd cannot read is at least as strict as `--action` with no `--branch` (`level_on_any_branch`),
   over a grammar of push lines in a repository, also with a detached HEAD.
2. A command's level equals its action's level on the branch the command reaches, for every command pattern of every
   built-in action: `--command` and `--action` agree.
3. A push with no refspec reads what git's settings send (`push.default`, `remote.<name>.push`, `pushRemote`, the upstream),
   never always the branch checked out.
4. A program by its Windows name (`git.exe`, `C:\\Git\\bin\\git.exe`) reads as the program.
5. A command that no action matches says so in `notes`, and a `--folder` that is no checkout says so.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import tempfile
import unittest
from pathlib import Path

import escape_table
import helpers

from aidd import risk
from aidd.kernel import json_schema
from aidd.risk import rules

RS = risk.rule_set(None)
LEVEL = {"allow": 0, "report": 1, "ask": 2}


def entries(line: str, cwd: str | None, branch: str | None = None) -> list[dict]:
    return risk.command_level(RS, line, branch=branch, cwd=cwd)["actions"]


def level(line: str, cwd: str) -> str:
    return risk.command_level(RS, line, cwd=cwd)["level"]


class ARepositoryCase(unittest.TestCase):
    """A repository on `feat`, whose upstream is `origin/main`, with a remote `origin`, and git's settings put back after each row."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = str(Path(cls.tmp.name).resolve() / "repo")
        Path(cls.repo).mkdir()
        helpers.git(cls.repo, "init", "-q", "-b", "main")
        Path(cls.repo, "notes.txt").write_text("x\n", encoding="utf-8")
        helpers.git(cls.repo, "add", "-A")
        helpers.git(cls.repo, "commit", "-q", "-m", "base")
        helpers.git(cls.repo, "remote", "add", "origin", "https://example.invalid/origin.git")
        for branch in ("main", "feat"):
            helpers.git(cls.repo, "update-ref", f"refs/remotes/origin/{branch}", "HEAD")
        helpers.git(cls.repo, "switch", "-q", "-c", "feat")
        helpers.git(cls.repo, "branch", "-q", "-u", "origin/main", "feat")
        cls.config_file = Path(cls.repo, ".git", "config")
        cls.base_config = cls.config_file.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        helpers.git(self.repo, "switch", "-q", "feat")
        self.addCleanup(self.reset)

    def reset(self):
        self.config_file.write_text(self.base_config, encoding="utf-8")


class ABranchAiddCannotReadIsTheStrictestTests(ARepositoryCase):
    REMOTES = ("", "origin")
    REFSPECS = ("", "feat", "HEAD", "$B", "$(rev-parse HEAD)", "@{u}", ":x", "'*'")
    FLAGS = ("", "--force-with-lease")

    def lines(self):
        for remote, refspec, flag in itertools.product(self.REMOTES, self.REFSPECS, self.FLAGS):
            if refspec and not remote:
                continue  # a refspec follows a remote
            yield " ".join(w for w in ("git push", flag, remote, refspec) if w)

    def test_no_push_entry_reads_an_unknown_branch_as_allow(self):
        # The invariant: an entry with no branch is the highest level over every branch, as `--action` says it.
        for detached in (False, True):
            if detached:
                helpers.git(self.repo, "switch", "-q", "--detach")
            for line in self.lines():
                with self.subTest(line=line, detached=detached):
                    for e in entries(line, self.repo):
                        if e["environment"] is None and e["branch"] is None:
                            self.assertEqual(e["level"], risk.level_on_any_branch(RS, e["action"])[0], e)

    def test_a_detached_head_pushes_a_branch_nobody_can_name(self):
        helpers.git(self.repo, "switch", "-q", "--detach")
        for line in ("git push", "git push origin", "git push -u origin", "git push --force-with-lease origin"):
            with self.subTest(line=line):
                self.assertEqual(level(line, self.repo), "ask")

    def test_the_branch_checked_out_stays_allowed_when_aidd_can_read_it(self):
        for line in ("git push", "git push origin", "git push -u origin feat", "git push origin HEAD", "git push origin feat"):
            with self.subTest(line=line):
                self.assertEqual(level(line, self.repo), "allow")


class APushWithNoRefspecReadsGitsSettingsTests(ARepositoryCase):
    # (git settings, the line, its level): on `feat`, which tracks `origin/main`.
    ROWS = (
        ({}, "git push", "allow"),
        ({"push.default": "simple"}, "git push", "allow"),
        ({"push.default": "current"}, "git push", "allow"),
        ({"push.default": "nothing"}, "git push", "allow"),  # it sends nothing
        ({"push.default": "upstream"}, "git push", "ask"),  # to origin/main
        ({"push.default": "tracking"}, "git push", "ask"),
        ({"push.default": "upstream", "branch.feat.merge": "refs/heads/feat"}, "git push", "ask"),  # the setting is read, not where it leads
        ({"push.default": "matching"}, "git push", "ask"),
        ({"remote.origin.push": "refs/heads/feat:refs/heads/main"}, "git push", "ask"),
        ({"remote.origin.push": "refs/heads/feat:refs/heads/main"}, "git push origin", "ask"),
        ({"remote.origin.push": "refs/heads/feat:refs/heads/feat"}, "git push", "ask"),
        ({"remote.origin.push": "HEAD"}, "git push", "ask"),
        ({"remote.origin.push": "+refs/heads/*:refs/heads/*"}, "git push", "ask"),
        ({"remote.other.push": "refs/heads/feat:refs/heads/main"}, "git push origin", "allow"),  # another remote's setting
        ({"remote.other.push": "refs/heads/feat:refs/heads/main", "branch.feat.pushRemote": "other"}, "git push", "ask"),
        ({"remote.other.push": "refs/heads/feat:refs/heads/main", "remote.pushDefault": "other"}, "git push", "ask"),
        ({"push.default": "matching"}, "git push origin feat", "ask"),  # a redirecting setting raises a push with a refspec too
    )

    def test_each_row(self):
        for settings, line, expected in self.ROWS:
            with self.subTest(settings=settings, line=line):
                for key, value in settings.items():
                    helpers.git(self.repo, "config", "--local", key, value)
                try:
                    self.assertEqual(level(line, self.repo), expected)
                finally:
                    self.reset()

    def test_the_default_branch_checked_out_still_asks_whatever_the_settings(self):
        helpers.git(self.repo, "switch", "-q", "main")
        for settings in ({}, {"push.default": "current"}, {"remote.origin.push": "refs/heads/main:refs/heads/other"}):
            with self.subTest(settings=settings):
                for key, value in settings.items():
                    helpers.git(self.repo, "config", "--local", key, value)
                try:
                    self.assertEqual(level("git push", self.repo), "ask")
                finally:
                    self.reset()


class CommandAndActionAgreeTests(unittest.TestCase):
    """For every command pattern of every built-in action, `--command` gives the level `--action` gives for the branch it reaches."""

    @staticmethod
    def concrete(pattern: str) -> list[str]:
        return list(dict.fromkeys(" ".join(pattern.replace("*", fill).split()) for fill in ("", "x")))

    def cases(self):
        for action, spec in RS.actions.items():
            for pattern in spec.get("commands", []):
                for line in self.concrete(pattern):
                    yield action, line

    def test_a_branch_the_person_names_reads_as_the_action_reads_it(self):
        compared = set()
        for action, line in self.cases():
            for branch in rules.BRANCHES:
                found = [e for e in entries(line, None, branch) if e["action"] == action and e["environment"] is None]
                for e in found:
                    with self.subTest(action=action, line=line, branch=branch):
                        compared.add(action)
                        want = risk.level_on_any_branch(RS, action, branch=branch)[0]
                        self.assertEqual(e["level"], want, e)
        self.assertGreater(len(compared), 15, "the table reaches many actions")

    def test_a_branch_nobody_names_reads_as_the_action_reads_it_with_no_branch(self):
        compared = set()
        for action, line in self.cases():
            if action.startswith(("git.push", "git.merge")):
                continue  # these read the branch from git: the first class holds them
            for e in entries(line, None):
                if e["action"] == action and e["environment"] is None:
                    with self.subTest(action=action, line=line):
                        compared.add(action)
                        self.assertEqual(e["level"], risk.level_on_any_branch(RS, action)[0], e)
        self.assertGreater(len(compared), 15, "the table reaches many actions")


class ABackslashEscapeNeverLowersALevelTests(unittest.TestCase):
    """A backslash before a character of a program or a subcommand, bare or inside a wrapper aidd reads, never lowers a level.

    To a POSIX shell, `g\\h pr merge 3` is `gh pr merge 3`. The table is held to the reader as it was before this change, too."""

    def test_the_two_commands_an_earlier_windows_reading_lowered(self):
        for line, action in (("g\\h pr merge 3", "pr.merge"), ("gi\\t push --force origin main", "git.push.force")):
            with self.subTest(line=line):
                self.assertIn(action, {e["action"] for e in entries(line, None, "own")})
                self.assertEqual(risk.command_level(RS, line, cwd=None)["level"], "ask")

    def test_an_escape_in_the_program_or_the_subcommand_is_never_read_lower(self):
        read, lower = escape_table.lower_rows(lambda c: risk.command_level(RS, c, cwd=None)["level"], limit=30)
        self.assertGreater(read, 1000, "the table reaches many commands and every wrapper")
        self.assertEqual(lower, [])


class AnAllowThatNoRuleGaveSaysSoTests(ARepositoryCase):
    def answer(self, *argv: str) -> tuple[int, dict]:
        with contextlib.chdir(self.repo):
            code, out = helpers.run_cli("risk", *argv, "--json")
        return code, json.loads(out)

    def test_a_command_no_action_matches_carries_a_note_in_the_json(self):
        for line in ("psql -c 'drop table users'", "ls -la", "echo hi"):
            with self.subTest(line=line):
                code, answer = self.answer("--command", line)
                self.assertEqual((code, answer["level"], answer["actions"]), (0, "allow", []))
                self.assertTrue(any("no action" in n for n in answer["notes"]), answer["notes"])
                self.assertEqual(json_schema.validate(answer, "risk.schema.json"), [])

    def test_a_program_by_its_windows_name_reads_as_no_action_and_says_so(self):
        """Safe because the answer says no rule matched, never that the command is allowed by a rule: aidd's command reader models
        a POSIX shell, so a Windows program name (`git.exe`, a path with backslashes, `bash.exe -c ...`) is a program it does not know.
        A second shell grammar inside the reader would open parser differentials; a Windows agent relies on its harness's ask rules."""
        for line in (
            "git.exe push --force origin main",
            "GIT.EXE push --force origin main",
            r"C:\Git\bin\git.exe push --force origin main",
            r'"C:\Program Files\Git\bin\git.exe" push --force origin main',
            r"bash.exe -c 'git push --force origin main'",
            "env.exe git push --force origin main",
            "gh.exe pr merge 3",
        ):
            with self.subTest(line=line):
                code, answer = self.answer("--command", line)
                self.assertEqual((code, answer["level"], answer["actions"]), (0, "allow", []))
                self.assertTrue(any("no action" in n for n in answer["notes"]), answer["notes"])

    def test_a_command_an_action_matches_carries_no_such_note(self):
        code, answer = self.answer("--command", "git push origin feat")
        self.assertEqual((code, answer["level"]), (0, "allow"))
        self.assertFalse(any("no action" in n for n in answer["notes"]), answer["notes"])

    def test_the_action_answer_has_no_constant_known_field(self):
        code, answer = self.answer("--action", "git.push")
        self.assertEqual(code, 0)
        self.assertNotIn("known", answer)
        self.assertEqual(json_schema.validate(answer, "risk.schema.json"), [])

    def test_a_folder_that_is_no_checkout_says_so_and_asks(self):
        missing = str(Path(self.tmp.name) / "missing")
        plain = Path(self.tmp.name) / "plain"
        plain.mkdir()
        for folder, why in ((missing, "is not a folder"), (str(plain), "is not a git checkout")):
            with self.subTest(folder=folder):
                code, answer = self.answer("--command", "git push", "--folder", folder)
                self.assertEqual((code, answer["level"]), (0, "ask"))
                self.assertTrue(any(why in n and folder in n for n in answer["notes"]), answer["notes"])

    def test_a_folder_that_is_a_checkout_adds_no_such_note(self):
        code, answer = self.answer("--command", "git push", "--folder", self.repo)
        self.assertEqual(code, 0)
        self.assertFalse(any("--folder" in n for n in answer["notes"]), answer["notes"])


if __name__ == "__main__":
    unittest.main()
