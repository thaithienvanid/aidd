"""Worktrees you can manage (V23, V24): each worktree's work item and state, read from git; `aidd worktrees clean`
removes only the missing and the merged ones, after a person's yes, never a branch or uncommitted work; AIDD_WORKTREE
names a worktree in the shared dev stack."""

import contextlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import git
from test_local_first import at_a_terminal

from aidd.cli import app
from aidd.guard import approval_commands
from aidd.platforms import local_ship
from aidd.workitems import worktree_list

NOT_AN_AGENT = {v: "" for v in local_ship.AGENT_ENV}


@unittest.skipUnless(shutil.which("git"), "git is required")
class WorktreeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.root = str(self.base / "main")
        os.mkdir(self.root)
        git(self.root, "init", "-q", "-b", "main")
        for k, v in (("user.email", "me@example.com"), ("user.name", "Me"), ("commit.gpgsign", "false")):
            git(self.root, "config", k, v)
        Path(self.root, "a.txt").write_text("a\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "first")

    def add(self, name: str, branch: str, *, commit: bool = True) -> str:
        path = str(self.base / name)
        git(self.root, "worktree", "add", "-q", "-b", branch, path)
        if commit:
            Path(path, f"{name}.txt").write_text("x\n", encoding="utf-8")
            git(path, "add", "-A")
            git(path, "commit", "-qm", f"work in {name}")
        return path

    def states(self) -> dict[str, str]:
        return {Path(r["path"]).name: r["state"] for r in worktree_list.worktree_states(self.root)}

    def test_each_worktree_has_a_work_item_and_a_state(self):
        merged = self.add("merged", "spec/SPEC-1")
        git(self.root, "merge", "-q", "--ff-only", "spec/SPEC-1")
        Path(self.root, "b.txt").write_text("b\n", encoding="utf-8")  # the base moves past it
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "later")
        self.add("active", "spec/SPEC-2")
        dirty = self.add("dirty", "spec/SPEC-3")
        Path(dirty, "wip.txt").write_text("wip\n", encoding="utf-8")
        gone = self.add("gone", "spec/SPEC-4")
        shutil.rmtree(gone)
        self.add("fresh", "spec/SPEC-5", commit=False)
        with mock.patch.object(worktree_list.git, "default_base", return_value="main"):
            rows = {Path(r["path"]).name: r for r in worktree_list.worktree_states(self.root)}
        self.assertEqual(
            {k: r["state"] for k, r in rows.items()},
            {"main": "new", "merged": "merged", "active": "active", "dirty": "uncommitted work", "gone": "missing", "fresh": "new"},
        )
        self.assertEqual(rows["active"]["item"], "SPEC-2")
        self.assertTrue(rows["main"]["main"])
        # Only the missing and the merged go; never the main worktree or the one it runs in.
        gone_ones = {Path(r["path"]).name for r in worktree_list.cleanable(list(rows.values()), merged)}
        self.assertEqual(gone_ones, {"gone"})
        self.assertEqual({Path(r["path"]).name for r in worktree_list.cleanable(list(rows.values()), self.root)}, {"gone", "merged"})

    def test_the_slug_is_stable_and_safe(self):
        slug = worktree_list.worktree_slug("/tmp/My Work Tree!")
        self.assertRegex(slug, r"^my_work_tree_[0-9a-f]{6}$")
        self.assertEqual(slug, worktree_list.worktree_slug("/tmp/My Work Tree!"))
        self.assertNotEqual(slug, worktree_list.worktree_slug("/other/My Work Tree!"))

    def test_only_the_person_cleans_and_git_keeps_uncommitted_work(self):
        self.add("merged", "spec/SPEC-1")
        git(self.root, "merge", "-q", "--ff-only", "spec/SPEC-1")
        Path(self.root, "b.txt").write_text("b\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "later")
        self.assertIsNotNone(approval_commands.forbidden_action("aidd worktrees clean"))
        self.assertIsNone(approval_commands.forbidden_action("aidd worktrees clean --dry-run"))
        self.assertIsNone(approval_commands.forbidden_action("aidd worktrees --json"))
        teardown_log = self.base / "teardown.log"
        cfg = Path(self.root, ".aidd")
        cfg.mkdir()
        teardown = [sys.executable, "-c", f"import os; open({str(teardown_log)!r}, 'a').write(os.environ['AIDD_WORKTREE'] + '\\n')"]
        (cfg / "config.yaml").write_text(
            'aidd_version: "1.0.0"\nprofile: solo\nowners:\n  approvers: ["email:me@example.com"]\nproject:\n  dev_services:\n'
            f"    teardown: {json.dumps(teardown)}\n",
            encoding="utf-8",
        )
        with contextlib.chdir(self.root), mock.patch.object(worktree_list.git, "default_base", return_value="main"):
            with mock.patch.dict(os.environ, NOT_AN_AGENT), at_a_terminal() as (out, err, _):
                self.assertEqual(app.main(["worktrees", "clean"]), 0, out.getvalue() + err.getvalue())
        self.assertFalse((self.base / "merged").exists())
        self.assertIn("spec/SPEC-1", git(self.root, "branch", "--list", "spec/SPEC-1"))  # the branch stays
        self.assertEqual(teardown_log.read_text(encoding="utf-8").split(), [worktree_list.worktree_slug(str(self.base / "merged"))])


if __name__ == "__main__":
    unittest.main()
