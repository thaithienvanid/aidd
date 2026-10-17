"""The guard on a goal branch and before Spec approval: a goal branch moves only through `aidd integrate`, `aidd sync`,
or a commit of plan files; a Task's scope opens once the Spec's approval holds."""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from helpers import RepoTemplateCase, git, make_repo

from aidd.guard import approval_commands, edit_check


@unittest.skipUnless(shutil.which("git"), "git is required")
class GoalBranchTests(RepoTemplateCase):
    """A team repository on goal/booking, with a branch spec/SPEC-1 cut from it."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", branch="goal/booking")
        (root / "specs" / "INIT-1.md").write_text("---\nkind: initiative\nid: INIT-1\ntitle: Booking\n---\n", encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-qm", "plan: booking")
        git(root, "branch", "spec/SPEC-1")

    def denial(self, command: str) -> str | None:
        return approval_commands.forbidden_action(command, str(self.root))

    def test_only_aidd_moves_a_goal_branch(self):
        for command in (
            "git merge spec/SPEC-1",
            "git cherry-pick spec/SPEC-1",
            "git reset --hard HEAD~1",
            "git rebase main",
            "git commit --allow-empty -m wip",
            "git push origin goal/booking",
            "git push origin HEAD",
            "git push",
            "git branch -f goal/booking spec/SPEC-1",
            "git branch -D goal/booking",
            "git update-ref refs/heads/goal/booking main",
            "git checkout -B goal/booking main",
            "git switch spec/SPEC-1 && git push origin spec/SPEC-1:goal/booking",
        ):
            why = self.denial(command)
            self.assertIsNotNone(why, command)
            self.assertIn("`aidd integrate`", why or "", command)

    def test_the_team_works_on_its_own_branches_and_through_aidd(self):
        for command in (
            "aidd integrate",
            "aidd sync",
            "git switch spec/SPEC-1 && git merge goal/booking",
            "git switch spec/SPEC-1 && git commit --allow-empty -m wip",
            "git push origin spec/SPEC-1",
            "git reset -- specs/INIT-1.md",
            "git checkout -b goal/new",
            "git log goal/booking",
        ):
            self.assertIsNone(self.denial(command), command)

    def test_no_spelling_moves_it_by_hand(self):
        """Every way the guard can read: the branch a command acts on through `cd`, `git -C`, and `GIT_DIR`; a push of
        every branch or by a pattern; a fetch into it; a rebase or a worktree that names it."""
        spec_wt = self.root.parent / "spec-wt"
        git(self.root, "worktree", "add", "-q", str(spec_wt), "spec/SPEC-1")
        goal = str(self.root)
        for command in (
            f"git -C {goal} merge spec/SPEC-1",
            f"cd {goal} && git merge spec/SPEC-1",
            f"GIT_DIR={goal}/.git GIT_WORK_TREE={goal} git commit --allow-empty -m wip",
            "git push --all origin",
            "git push origin 'refs/heads/*:refs/heads/*'",
            "git fetch . spec/SPEC-1:goal/booking",
            "git rebase main goal/booking",
            f"git worktree add -B goal/booking {self.root.parent / 'other'} main",
            "git symbolic-ref HEAD refs/heads/goal/booking && git commit --allow-empty -m wip",
            "git update-ref --stdin",
            # A repository, index, or folder only git or the shell resolves counts as every branch.
            "GIT_INDEX_FILE=/tmp/other-index git commit -m 'plan: rooms'",
            f"git --git-dir={goal}/.git merge spec/SPEC-1",
            'cd "$GOAL" && git merge spec/SPEC-1',
            "cd ~/goal && git merge spec/SPEC-1",
            f"env -C {goal} git merge spec/SPEC-1",
            f"pushd {goal} && git merge spec/SPEC-1",
            f"export GIT_DIR={goal}/.git && git merge spec/SPEC-1",
            # A push with no refspec goes where the config says: the branch's upstream may be the goal.
            "git config branch.spec/SPEC-1.merge refs/heads/goal/booking; git push",
            "git branch -u origin/goal/booking",
        ):
            self.assertIsNotNone(approval_commands.forbidden_action(command, str(spec_wt)), command)
        git(spec_wt, "config", "branch.spec/SPEC-1.merge", "refs/heads/goal/booking")
        self.assertIsNotNone(approval_commands.forbidden_action("git push", str(spec_wt)))
        git(spec_wt, "config", "--unset", "branch.spec/SPEC-1.merge")
        for command in (
            f"cd {goal} && git log",
            "git fetch origin",
            "git push origin spec/SPEC-1",
            f"(cd {goal}) && git merge main",
            "git pull --ff-only",
            "GIT_AUTHOR_NAME=me git commit --allow-empty -m wip",
        ):
            self.assertIsNone(approval_commands.forbidden_action(command, str(spec_wt)), command)

    def test_a_commit_of_plan_files_alone_may_land_on_the_goal(self):
        (self.root / "specs" / "EPIC-1.md").write_text("---\nkind: epic\nid: EPIC-1\ntitle: Rooms\n---\n", encoding="utf-8")
        git(self.root, "add", "specs/EPIC-1.md")
        self.assertIsNone(self.denial("git commit -m 'plan: rooms'"))
        Path(self.root, "app.py").write_text("x = 1\n", encoding="utf-8")
        git(self.root, "add", "app.py")
        self.assertIsNotNone(self.denial("git commit -m 'plan: rooms'"))  # code rides along: not a plan commit
        git(self.root, "reset", "-q", "app.py")
        git(self.root, "add", "-N", "app.py")
        self.assertIsNotNone(self.denial("git commit -am 'plan: rooms'"))
        git(self.root, "reset", "-q", "app.py")
        # What a command before it stages is not in the index yet: a plan commit runs alone, and never amends.
        self.assertIsNotNone(self.denial("git add app.py && git commit -m 'plan: rooms'"))
        self.assertIsNotNone(self.denial("git commit --amend -m 'plan: rooms'"))
        self.assertIsNotNone(self.denial("git commit --pathspec-from-file=list -m 'plan: rooms'"))


SPEC = """---
aidd_version: "1.0.0"
kind: spec
id: SPEC-1
title: Hold a room
owner_team: core
type: feat
route: normal
confidence: high
open_questions: []
trace_id: spec-1
assisted_by: []
rollback: Revert the PR.
risk:
  summary: Holds a room.
  dimensions: []
  reversible: true
tasks:
  - id: TASK-1
    title: Hold
    scope: [src/rooms/, "specs/SPEC-1/runbook-hold.md"]
docs:
  - kind: runbook
    path: specs/SPEC-1/runbook-hold.md
    frozen: false
tests:
  files: [tests/test_rooms.py]
---

## Intent

Hold a room.
"""


@unittest.skipUnless(shutil.which("git"), "git is required")
class WaitsForSpecApprovalTests(RepoTemplateCase):
    """No implementation edit before Spec approval, where the profile asks for one (team: normal and major)."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team")
        (root / "specs" / "SPEC-1.md").write_text(SPEC, encoding="utf-8")

    def decide(self, role: str | None, rel: str) -> tuple[str, str]:
        return edit_check.check_edit(str(self.root), rel, role)[:2]

    def set_status(self, status: str) -> None:
        p = self.root / "specs" / "SPEC-1.md"
        p.write_text(SPEC.replace("route: normal", f'route: normal\nstatus: "{status}"', 1), encoding="utf-8")

    def test_the_code_waits_for_the_contract(self):
        decision, why = self.decide("developer", "src/rooms/hold.py")
        self.assertEqual(decision, "deny")
        self.assertIn("waits for Spec approval", why)
        self.assertIn("aidd new exploration", why)
        self.assertEqual(self.decide(None, "src/rooms/hold.py")[0], "deny")  # the main session too

    def test_the_contract_is_written_first(self):
        self.assertEqual(self.decide("tester", "tests/test_rooms.py")[0], "allow")
        # A document the Spec lists is its own paperwork, even inside a Task's scope.
        self.assertEqual(self.decide("sre", "specs/SPEC-1/runbook-hold.md")[0], "allow")

    def test_a_wide_scope_keeps_the_tests_first(self):
        p = self.root / "specs" / "SPEC-1.md"
        p.write_text(SPEC.replace('scope: [src/rooms/, "specs/SPEC-1/runbook-hold.md"]', "scope: [src/rooms/, tests/]", 1), encoding="utf-8")
        self.assertEqual(self.decide("tester", "tests/test_rooms.py")[0], "allow")
        self.assertEqual(self.decide("developer", "tests/helpers_rooms.py")[0], "deny")  # in scope, not a listed test
        p.write_text(SPEC.replace("files: [tests/test_rooms.py]", "files: [tests/test_rooms.py, src/rooms/hold.py]", 1), encoding="utf-8")
        self.assertEqual(self.decide("developer", "src/rooms/hold.py")[0], "deny")  # code listed as a test still waits

    def test_approval_opens_the_scope(self):
        self.set_status("ready")
        self.assertEqual(self.decide("developer", "src/rooms/hold.py")[0], "allow")

    def test_a_spec_never_lists_product_code_as_its_paperwork(self):
        p = self.root / "specs" / "SPEC-1.md"
        for listed in (
            SPEC.replace("    path: specs/SPEC-1/runbook-hold.md\n", "    path: src/rooms/hold.py\n", 1),
            SPEC.replace("\ntests:", '\ndesign:\n  files: ["src/rooms/**"]\ntests:', 1),
            SPEC.replace("\ntests:", '\ndesign:\n  files: ["specs/../src/rooms/**"]\ntests:', 1),
        ):
            p.write_text(listed, encoding="utf-8")
            decision, why = self.decide("developer", "src/rooms/hold.py")
            self.assertEqual(decision, "deny", listed)
            self.assertIn("waits for Spec approval", why)

    def test_a_route_with_no_spec_approval_never_waits(self):
        p = self.root / "specs" / "SPEC-1.md"
        p.write_text(SPEC.replace("route: normal", "route: minor", 1), encoding="utf-8")
        self.assertEqual(self.decide("developer", "src/rooms/hold.py")[0], "allow")


if __name__ == "__main__":
    unittest.main()
