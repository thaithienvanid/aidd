"""Explore branches: free work that never merges as it is. The guard holds no edit on an `explore/` branch, only a
person starts one, and the gate, `aidd ship`, and `aidd integrate` refuse a change from one."""

from __future__ import annotations

import contextlib
import shutil
import unittest

from helpers import RepoTemplateCase, git, make_repo, run_cli

from aidd import gate, platforms, workitems
from aidd.guard import approval_commands, command_check, edit_check

PROTECTED = ".github/workflows/deploy.yml"


@unittest.skipUnless(shutil.which("git"), "git is required")
class ExploreBranchTests(RepoTemplateCase):
    """A team repository with a branch `feat` and an explore branch `explore/cache`, each one commit ahead of main."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team")
        (root / "notes.md").write_text("an idea\n", encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-qm", "an idea")
        git(root, "branch", "explore/cache")

    def on_explore(self):
        git(self.root, "switch", "-q", "explore/cache")

    def test_the_guard_frees_every_edit_on_an_explore_branch_only(self):
        held = edit_check.check_edit(str(self.root), PROTECTED)
        self.assertEqual(held[0], "deny", held)
        self.on_explore()
        free = edit_check.check_edit(str(self.root), PROTECTED)
        self.assertEqual(free[0], "allow", free)
        self.assertIn("explore branch", free[1])

    def test_an_agent_never_loosens_the_config_there(self):
        self.on_explore()
        cfg = (self.root / ".aidd" / "config.yaml").read_text(encoding="utf-8")
        loosened = cfg.replace("profile: team", "profile: solo")
        self.assertNotEqual(loosened, cfg)
        event = {"tool_name": "Write", "tool_input": {"file_path": str(self.root / ".aidd" / "config.yaml"), "content": loosened}}
        self.assertEqual(edit_check.check_agent_edit(str(self.root), ".aidd/config.yaml", event)[0], "deny")

    def test_only_a_person_starts_one_or_switches_to_one(self):
        for command in (
            "git switch -c explore/other",
            "git checkout -b explore/other",
            "git switch explore/cache",
            "git checkout explore/cache",
            "git branch -m explore/other",
            "git branch -m feat explore/other",
            f"git worktree add -b explore/other {self.root.parent / 'w'}",
            f"git worktree add {self.root.parent / 'w'} explore/cache",
            "git symbolic-ref HEAD refs/heads/explore/cache",
            "git switch -qc explore/other",  # bundled short flags
            "git checkout --track origin/explore/cache",
            "git rebase main explore/cache",
            "git stash branch explore/other",
            "git config alias.go 'switch explore/cache'",
            "git go explore/cache",  # an alias
            "git checkout explore/cache --",
            "git branch -fm explore/other",  # bundled
            "git branch --mov explore/other",  # an abbreviated long option
            "git checkout -bexplore/other",  # a value attached to its option
            "gh pr checkout 7 --branch explore/other",
        ):
            why = approval_commands.forbidden_action(command, str(self.root))
            self.assertIsNotNone(why, command)
            self.assertIn("only a person starts one", why or "", command)
        for unreadable in ('git switch "$TOPIC"', "git switch -", "git checkout @{-1}", 'git branch -m "$NAME"', 'git sw "$TOPIC"'):
            self.assertIn("name it plainly", approval_commands.forbidden_action(unreadable, str(self.root)) or "", unreadable)
        self.assertIsNotNone(approval_commands.forbidden_action("git switch --create explore/other", str(self.root)))
        self.assertIn("--branch review/", approval_commands.forbidden_action("gh pr checkout 7", str(self.root)) or "")
        for command in (
            "git switch -c fix/cache",
            "git log explore/cache",
            "git diff main explore/cache",
            "git checkout explore/cache -- notes.md",
            "git branch -m fix/cache",
            "git branch explore/later",
            "git push origin explore/cache",
            "gh pr checkout 7 --branch review/7",
            'git commit -m "$MESSAGE"',
            "git branch -d explore/cache",
        ):
            self.assertIsNone(approval_commands.forbidden_action(command, str(self.root)), command)

    def test_an_alias_never_hides_a_switch_to_one(self):
        """From a security review: a one-off alias (`-c alias.x=...`), an alias kept in git config, and a shell alias
        that reads a variable all expand only when git runs them, so the guard reads them first, failing closed."""
        git(self.root, "config", "alias.sh", "!git checkout $B")
        git(self.root, "config", "alias.co", "checkout")
        git(self.root, "config", "alias.st", "status -sb")
        for command in (
            "git -c alias.x='checkout explore/y' x",
            "git -c 'alias.x=!git checkout explore/y' x",
            "git -calias.x=switch x explore/y",
            "git --config-env alias.x=VAR x",
            "git --config-env=alias.x=VAR x",
            "B=explore/y git sh",
            "git sh",
            "git co explore/y",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(approval_commands.forbidden_action(command, str(self.root)), command)
        for command in ("git st", "git co fix/cache", "git -c core.pager=cat log"):
            with self.subTest(command=command):
                self.assertIsNone(approval_commands.forbidden_action(command, str(self.root)), command)

    def test_the_guards_own_wiring_stays_a_persons_there(self):
        self.on_explore()
        for rel in (".claude/settings.json", ".agents/hooks.json"):
            decision, reason = edit_check.check_edit(str(self.root), rel)
            self.assertEqual(decision, "deny", rel)
            self.assertIn("loads aidd's guard", reason)
        command = "echo '{}' > .claude/settings.json"
        event = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(self.root), "agent_type": "aidd-team:developer"}
        self.assertEqual(command_check.check_command(str(self.root), str(self.root), command, event)[0], "deny")
        free = "echo note > notes.md"
        event["tool_input"]["command"] = free
        self.assertEqual(command_check.check_command(str(self.root), str(self.root), free, event)[0], "allow")

    def test_a_role_never_writes_head_by_hand(self):
        """A HEAD written with the shell could name an explore branch: only git and aidd commands write in .git."""
        command = "echo 'ref: refs/heads/explore/cache' > .git/HEAD"
        event = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(self.root), "agent_type": "aidd-team:developer"}
        decision, reason = command_check.check_command(str(self.root), str(self.root), command, event)
        self.assertEqual(decision, "deny", reason)
        self.assertIn("inside the git directory", reason)

    def test_the_gate_fails_a_change_from_an_explore_branch(self):
        self.on_explore()
        with contextlib.chdir(self.root):
            ctx = platforms.build_local_context(run_policy=False)
            self.assertEqual(ctx["change"]["head_ref"], "explore/cache")
            found = [f.code for f in gate.decide(ctx).findings]
            self.assertIn("explore.branch", found)
            head = git(self.root, "rev-parse", "HEAD")
            self.assertEqual(platforms.build_local_context(head=head, run_policy=False)["change"]["head_ref"], "explore/cache")
            git(self.root, "switch", "-q", "--detach")  # a detached HEAD, or a bare commit, at an explore branch's tip
            self.assertEqual(platforms.build_local_context(head=head, run_policy=False)["change"]["head_ref"], "explore/cache")
            git(self.root, "switch", "-q", "explore/cache")
            git(self.root, "branch", "-m", "spike/cache")  # renamed: checked as any change
            ctx = platforms.build_local_context(run_policy=False)
            self.assertEqual(ctx["change"]["head_ref"], "spike/cache")
            self.assertNotIn("explore.branch", [f.code for f in gate.decide(ctx).findings])

    def test_ship_refuses_it_and_says_how_to_keep_the_work(self):
        self.on_explore()
        with contextlib.chdir(self.root):
            code, out = run_cli("ship")
        self.assertEqual(code, 1, out)
        self.assertIn("explore/cache is an explore branch", out)
        self.assertIn("git branch -m", out)

    def test_aidd_list_and_the_note_name_it(self):
        self.on_explore()
        self.assertTrue(workitems.is_explore(workitems.current_branch(str(self.root))))
        with contextlib.chdir(self.root):
            code, out = run_cli("list", "--json")
        self.assertEqual(code, 0, out)
        self.assertIn('"explore_branch": "explore/cache"', out)
        self.assertIn("nothing merges from it", workitems.explore_note("explore/cache"))


@unittest.skipUnless(shutil.which("git"), "git is required")
class LoopOffInTheConfigTests(RepoTemplateCase):
    """With `components.loop: false`, every edit is free already, so switching to an explore branch is no one's call."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team")
        path = root / ".aidd" / "config.yaml"
        path.write_text(path.read_text(encoding="utf-8") + "components:\n  loop: false\n", encoding="utf-8")

    def test_switching_to_an_explore_branch_is_allowed(self):
        self.assertIsNone(approval_commands.forbidden_action("git switch -c explore/other", str(self.root)))


if __name__ == "__main__":
    unittest.main()
