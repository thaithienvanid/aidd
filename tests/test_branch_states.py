"""The branch an action reads is one of three states, and no two share a value.

- The branch was read and is X: the level on X.
- The branch could not be read (a detached HEAD, no repository, none given): the strictest level over branches, as `--action` with no
  `--branch` gives it.
- The action never depends on a branch (no rule in force makes its level differ by branch): its plain level, as before.

The table crosses every action that has a command pattern, with a branch-scoped rule added in the test for each, against the states
a command meets: your own branch, the default branch, a shared branch, a detached HEAD, and a folder outside every repository. `git push`,
`git merge`, and `gh pr merge` read the branch they reach from their words, so the repository states leave them out.
"""

from __future__ import annotations

import contextlib
import json
import tempfile
import unittest
from pathlib import Path

import escape_table
import helpers

from unittest import mock

from aidd import config, risk
from aidd.kernel import git
from aidd.risk import rules

BUILTIN = risk.rule_set(None)
OWN_READ = ("git.push", "git.merge", "pr.merge")  # these read the branch they reach themselves
LINES = {}


def command_for(action: str) -> str | None:
    """A command line that is `action`, from one of its patterns."""
    for pattern in BUILTIN.actions[action].get("commands", []):
        for line in escape_table.concrete(pattern):
            if any(e["action"] == action for e in risk.command_level(BUILTIN, line, branch="own", cwd=None)["actions"]):
                return line
    return None


def with_a_branch_rule_for_every_action() -> tuple[risk.RuleSet, str]:
    names = [a for a in BUILTIN.actions if BUILTIN.actions[a].get("commands") and not any(r.branch for r in BUILTIN.rules if r.action == a)]
    text = 'aidd_version: "1.0.0"\nprofile: team\nrisks:\n  rules:\n' + "".join(f"    - {{action: {a}, branch: default, level: ask}}\n" for a in names)
    return risk.rule_set(config.load_text(text)), text


RULES, CONFIG_TEXT = with_a_branch_rule_for_every_action()


def entry_levels(rs: risk.RuleSet, action: str, **where) -> list[str]:
    line = LINES.get(action) or command_for(action)
    LINES[action] = line  # type: ignore[assignment]
    found = risk.command_level(rs, line, **where)["actions"] if line else []
    return [e["level"] for e in found if e["action"] == action and e["environment"] is None]


class TheBranchStatesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = str(Path(cls.tmp.name).resolve() / "repo")
        Path(cls.repo, ".aidd").mkdir(parents=True)
        Path(cls.repo, ".aidd", "config.yaml").write_text(CONFIG_TEXT, encoding="utf-8")
        helpers.git(cls.repo, "init", "-q", "-b", "main")
        Path(cls.repo, "notes.txt").write_text("x\n", encoding="utf-8")
        helpers.git(cls.repo, "add", "-A")
        helpers.git(cls.repo, "commit", "-q", "-m", "base")
        helpers.git(cls.repo, "switch", "-q", "-c", "feat")
        helpers.git(cls.repo, "switch", "-q", "main")
        helpers.git(cls.repo, "switch", "-q", "feat")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def actions(self, *, repository: bool) -> list[str]:
        return [a for a in BUILTIN.actions if BUILTIN.actions[a].get("commands") and command_for(a) and not (repository and a in OWN_READ) and a != "pr.merge"]

    def expect(self, rs: risk.RuleSet, action: str, state: str) -> str:
        if state in rules.BRANCHES:
            return risk.level_of(rs, action, branch=state)[0]  # readable
        return risk.level_on_any_branch(rs, action)[0]  # unreadable

    def check(self, rs: risk.RuleSet, state: str, repository: bool, **where) -> int:
        compared = 0
        for action in self.actions(repository=repository):
            with self.subTest(action=action, state=state):
                levels = entry_levels(rs, action, **where)
                self.assertTrue(levels, action)
                self.assertEqual(set(levels), {self.expect(rs, action, state)}, LINES[action])
                compared += 1
        return compared

    def test_a_branch_the_person_names_gives_that_branchs_level(self):
        for state in rules.BRANCHES:
            for rs in (BUILTIN, RULES):
                self.assertGreater(self.check(rs, state, False, branch=state, cwd=None), 15)

    def test_no_branch_in_no_repository_gives_the_strictest(self):
        for rs in (BUILTIN, RULES):
            self.assertGreater(self.check(rs, "unreadable", False, cwd=None), 15)

    def test_the_branch_checked_out_gives_its_level_and_a_detached_head_the_strictest(self):
        for switch, state in ((("switch", "feat"), "own"), (("switch", "main"), "default"), (("switch", "--detach"), "unreadable")):
            helpers.git(self.repo, *switch)
            self.assertGreater(self.check(RULES, state, True, cwd=self.repo), 15, state)
        helpers.git(self.repo, "switch", "feat")

    def test_the_review_row_a_commit_on_your_own_branch_is_allowed_and_on_the_default_branch_asks(self):
        for switch, expected in ((("switch", "feat"), "allow"), (("switch", "main"), "ask"), (("switch", "--detach"), "ask")):
            helpers.git(self.repo, *switch)
            self.assertEqual(risk.command_level(RULES, "git commit -m x", cwd=self.repo)["level"], expected, switch)
        helpers.git(self.repo, "switch", "feat")

    # A checkout earlier on the line: to a branch that exists, to the default branch, to a target aidd cannot read, to a new branch.
    CHECKOUTS = ("feat", "main", "-", "$B", "-b new")

    def checkout_level(self, rs: risk.RuleSet, action: str, session: str, target: str) -> str:
        """The strictest of the session branch and the checked-out one. A checkout to the branch already checked out moves nothing; to
        a branch that exists, it reads `shared`; to the default branch or a target aidd cannot read, `default`; `-b` makes a name
        move, so the branch cannot be read."""
        current = "feat" if session == "own" else "main"
        if target == "-b new":
            return risk.level_on_any_branch(rs, action)[0]
        if target == current:
            return risk.level_of(rs, action, branch=session)[0]
        landed = {"feat": "shared", "main": "default"}.get(target, "default")
        return max(risk.level_of(rs, action, branch=session)[0], risk.level_of(rs, action, branch=landed)[0], key=rules.LEVEL_RANK.__getitem__)

    def test_a_checkout_earlier_on_the_line_reads_beside_the_branch_checked_out(self):
        compared = 0
        for session, switch in (("own", "feat"), ("default", "main")):
            helpers.git(self.repo, "switch", switch)
            for action in self.actions(repository=True):
                command = LINES.get(action) or command_for(action)
                for target in self.CHECKOUTS:
                    with self.subTest(action=action, session=session, target=target):
                        levels = {
                            e["level"]
                            for e in risk.command_level(RULES, f"git checkout {target} && {command}", cwd=self.repo)["actions"]
                            if e["action"] == action
                        }
                        self.assertEqual(levels, {self.checkout_level(RULES, action, session, target)}, target)
                        compared += 1
        helpers.git(self.repo, "switch", "feat")
        self.assertGreater(compared, 100)

    def test_a_new_branch_on_the_default_branch_reads_as_a_push_does(self):
        # `git checkout -b feat2 && git push` from the default branch reads the default branch beside the new one, and the stricter wins; the
        # commit follows. On your own branch a commit after `-b` reads as unreadable, the strictest, because the checkout creates a ref.
        helpers.git(self.repo, "switch", "main")
        for command in ("git push", "git commit -m x"):
            self.assertEqual(risk.command_level(RULES, f"git checkout -b feat2 && {command}", cwd=self.repo)["level"], "ask", command)
        helpers.git(self.repo, "switch", "feat")
        self.assertEqual(risk.command_level(RULES, "git checkout -b feat2 && git push", cwd=self.repo)["level"], "allow")
        self.assertEqual(risk.command_level(RULES, "git checkout -b feat2 && git commit -m x", cwd=self.repo)["level"], "ask")

    def test_the_review_line_a_commit_after_a_checkout_of_the_default_branch_asks(self):
        self.assertEqual(risk.command_level(RULES, "git checkout main && git commit -m x", cwd=self.repo)["level"], "ask")
        self.assertEqual(risk.command_level(RULES, "git commit -m x", cwd=self.repo)["level"], "allow")

    def test_an_action_no_rule_makes_branch_dependent_ignores_a_checkout(self):
        plain = [a for a in self.actions(repository=True) if len({risk.level_of(BUILTIN, a, branch=b)[0] for b in rules.ANY_BRANCH}) == 1]
        self.assertGreater(len(plain), 8)
        for action in plain:
            for target in self.CHECKOUTS:
                with self.subTest(action=action, target=target):
                    line = f"git checkout {target} && {LINES.get(action) or command_for(action)}"
                    levels = {e["level"] for e in risk.command_level(BUILTIN, line, cwd=self.repo)["actions"] if e["action"] == action}
                    self.assertEqual(levels, {risk.level_of(BUILTIN, action)[0]})

    def test_an_ordinary_commit_makes_no_git_call_when_no_rule_makes_it_branch_dependent(self):
        with mock.patch.object(git, "_git", wraps=git._git) as calls:
            risk.command_level(BUILTIN, "git commit -m x", cwd=self.repo)
        self.assertEqual(calls.call_count, 0)
        with mock.patch.object(git, "_git", wraps=git._git) as calls:
            risk.command_level(RULES, "git commit -m x", cwd=self.repo)
        self.assertGreater(calls.call_count, 0, "a rule that names a branch needs the branch")

    def test_an_action_no_branch_changes_reads_as_it_always_did(self):
        plain = [a for a in self.actions(repository=False) if len({risk.level_of(BUILTIN, a, branch=b)[0] for b in rules.ANY_BRANCH}) == 1]
        self.assertGreater(len(plain), 8)
        for action in plain:
            for where in ({"cwd": None}, {"cwd": self.repo}, {"cwd": None, "branch": "own"}):
                with self.subTest(action=action, where=where):
                    self.assertEqual(set(entry_levels(BUILTIN, action, **where)), {risk.level_of(BUILTIN, action)[0]})

    def test_action_with_no_branch_agrees_with_command_when_the_branch_is_unreadable(self):
        helpers.git(self.repo, "switch", "--detach")
        try:
            with contextlib.chdir(self.repo):
                _, by_action = helpers.run_cli("risk", "--action", "git.commit", "--json")
                _, by_command = helpers.run_cli("risk", "--command", "git commit -m x", "--json")
            self.assertEqual(json.loads(by_action)["level"], json.loads(by_command)["level"])
            self.assertEqual(json.loads(by_command)["level"], "ask")
        finally:
            helpers.git(self.repo, "switch", "feat")


if __name__ == "__main__":
    unittest.main()
