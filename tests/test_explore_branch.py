"""Explore branches: free work that never merges as it is. The guard holds no edit on a `explore/` branch, only a
person starts one, and the gate, `aidd land`, and `aidd integrate` refuse a change from one. A branch named before
1.0's rename (`explore/`) is an ordinary branch now, and still nothing merges from it as it is."""

from __future__ import annotations

import contextlib
import shutil
import unittest

from helpers import TEST_APPROVER, check_agent_edit, check_edit, git, make_repo, RepoTemplateCase, run_cli

from aidd import gate, platforms, workitems
from aidd.guard import approval_commands, command_check

PROTECTED = ".github/workflows/deploy.yml"


@unittest.skipUnless(shutil.which("git"), "git is required")
class ExploreBranchTests(RepoTemplateCase):
    """A team repository with a branch `feat` and an explore branch `explore/cache`, each one commit ahead of main."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", approvers=[TEST_APPROVER])
        (root / "notes.md").write_text("an idea\n", encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-qm", "an idea")
        git(root, "branch", "explore/cache")

    def on_explore(self):
        """The person started `explore/cache` (their recorded `explore branch cache`), and the worktree is on it."""
        workitems.record_local_approval(workitems.explore_said_line("explore/cache"), str(self.root))
        git(self.root, "switch", "-q", "explore/cache")

    def test_a_explore_prefix_with_no_record_is_an_ordinary_branch(self):
        git(self.root, "switch", "-q", "explore/cache")  # a branch named so, which nobody started through aidd
        self.assertEqual(check_edit(str(self.root), PROTECTED)[0], "deny", "its edits are checked as on any branch")
        self.assertFalse(workitems.explore_started(workitems.config_at(self.root), str(self.root), "explore/cache"))
        self.assertIn("types `explore branch cache`", workitems.unstarted_explore_note("explore/cache"))
        self.assertIn("`explore branch <topic>`", workitems.unstarted_explore_note("explore/a/b"))  # never words the typed form refuses
        with contextlib.chdir(self.root):
            ctx = platforms.build_local_context(run_policy=False)
            self.assertIn("explore.branch", [f.code for f in gate.decide(ctx).findings], "and still nothing merges from it")
        workitems.record_local_approval(workitems.explore_said_line("explore/other"), str(self.root))  # another branch's record
        self.assertEqual(check_edit(str(self.root), PROTECTED)[0], "deny", "a record frees only the branch it names")
        self.on_explore()
        self.assertEqual(check_edit(str(self.root), PROTECTED)[0], "allow")

    def test_the_guard_frees_every_edit_on_a_explore_branch_only(self):
        held = check_edit(str(self.root), PROTECTED)
        self.assertEqual(held[0], "deny", held)
        self.on_explore()
        free = check_edit(str(self.root), PROTECTED)
        self.assertEqual(free[0], "allow", free)
        self.assertIn("explore branch", free[1])

    def test_an_agent_never_loosens_the_config_there(self):
        self.on_explore()
        cfg = (self.root / ".aidd" / "config.yaml").read_text(encoding="utf-8")
        loosened = cfg.replace("profile: team", "profile: solo")
        self.assertNotEqual(loosened, cfg)
        event = {"tool_name": "Write", "tool_input": {"file_path": str(self.root / ".aidd" / "config.yaml"), "content": loosened}}
        self.assertEqual(check_agent_edit(str(self.root), ".aidd/config.yaml", event)[0], "deny")

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
        for unreadable in ('git switch "$TOPIC"', "git switch -", "git checkout @{-1}", 'git sw "$TOPIC"'):
            self.assertIn("name it plainly", approval_commands.forbidden_action(unreadable, str(self.root)) or "", unreadable)
        # `$NAME` may split into `-f main`, which moves the base branch: that reason comes first.
        self.assertIsNotNone(approval_commands.forbidden_action('git branch -m "$NAME"', str(self.root)))
        # An alias is a person's setting, as a program git runs: that reason comes first.
        self.assertIn("alias", approval_commands.forbidden_action("git config alias.go 'switch explore/cache'", str(self.root)) or "")
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

    def test_the_persons_typed_words_start_one(self):
        from aidd.cli.commands import typed_decisions

        (self.root / "draft.md").write_text("half an idea\n", encoding="utf-8")
        note = typed_decisions.record("explore branch caching", str(self.root)) or ""
        self.assertIn("from their own words", note)
        self.assertEqual(git(self.root, "symbolic-ref", "--short", "HEAD"), "explore/caching")
        self.assertTrue(workitems.explore_started(workitems.config_at(self.root), str(self.root), "explore/caching"), "recorded as theirs")
        self.assertEqual(check_edit(str(self.root), PROTECTED)[0], "allow", "so its edits are free")
        self.assertTrue((self.root / "draft.md").is_file())  # the work in hand comes along
        self.assertIsNone(typed_decisions.record("explore auth", str(self.root)))  # an ordinary prompt stays one
        typed_decisions.record("explore branch cache", str(self.root))
        self.assertEqual(git(self.root, "symbolic-ref", "--short", "HEAD"), "explore/cache")  # the one that exists
        self.assertIn("could not record it", typed_decisions.record("explore branch a..b", str(self.root)) or "")
        # Typed into another terminal by an agent, it is held, as every typed decision is.
        self.assertIsNotNone(approval_commands.forbidden_action("tmux send-keys 'explore branch x' Enter", str(self.root)))

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
            decision, reason = check_edit(str(self.root), rel)
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

    def test_the_gate_fails_a_change_from_a_explore_branch(self):
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
            git(self.root, "branch", "-m", "feature/cache")  # renamed: checked as any change
            ctx = platforms.build_local_context(run_policy=False)
            self.assertEqual(ctx["change"]["head_ref"], "feature/cache")
            self.assertNotIn("explore.branch", [f.code for f in gate.decide(ctx).findings])

    def test_land_refuses_it_and_says_how_to_keep_the_work(self):
        self.on_explore()
        with contextlib.chdir(self.root):
            code, out = run_cli("land")
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
    """With `components.spec_steps: false`, every edit is free already, so switching to an explore branch is no one's call."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team")
        path = root / ".aidd" / "config.yaml"
        path.write_text(path.read_text(encoding="utf-8") + "components:\n  spec_steps: false\n", encoding="utf-8")

    def test_switching_to_a_explore_branch_is_allowed(self):
        self.assertIsNone(approval_commands.forbidden_action("git switch -c explore/other", str(self.root)))


if __name__ == "__main__":
    unittest.main()
