"""`aidd doctor` notes what a run left open on the machine: a worktree or a branch whose every commit is on the branch checked
out or on the default branch, and a scratch folder under `.aidd/tmp/` past its age, each with the command that closes it.

The invariant: doctor names a worktree or a branch only when git's own patch match (`git cherry`) puts every commit it holds
on a target, so a commit that landed after a conflict, or one that never landed, keeps it out; it never names the default
branch or the branch checked out; it reads only; and it says nothing when nothing is left over. It stays fast with many
worktrees: one git call for each."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import git

from aidd.kernel import git as kernel_git
from aidd.setup import doctor_checks, doctor_leftovers


def commit(root: Path, name: str, text: str) -> str:
    (root / name).write_text(text, encoding="utf-8")
    git(root, "add", name)
    git(root, "commit", "-q", "-m", f"{name}: {text.strip()}")
    return git(root, "rev-parse", "HEAD").strip()


def repository(base: Path) -> Path:
    root = base / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "T")
    commit(root, "a.txt", "one\n")
    return root


def worktree(root: Path, name: str) -> Path:
    """A worktree on a new branch, as a harness makes one for a role. The repository's config gives its commits an author."""
    path = root.parent / name
    git(root, "worktree", "add", "-q", "-b", name, str(path))
    return path


def lines(root: Path) -> list[str]:
    return [message for level, message in doctor_leftovers.leftover_lines(root) if level == "info"]


class LeftOpenWorktreesAndBranches(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = repository(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def named(self, what: str) -> list[str]:
        return [line for line in lines(self.root) if f" {what} " in line]

    def test_nothing_left_over_says_nothing(self):
        self.assertEqual(doctor_leftovers.leftover_lines(self.root), [])

    def test_a_worktree_is_named_only_when_git_puts_every_commit_on_a_target(self):
        picked = worktree(self.root, "role-picked")
        sha = commit(picked, "b.txt", "two\n")
        git(self.root, "cherry-pick", sha)  # brought over one commit at a time, as the lead does
        apart = worktree(self.root, "role-apart")
        commit(apart, "c.txt", "three\n")  # never landed
        conflicted = worktree(self.root, "role-conflicted")
        commit(conflicted, "a.txt", "one\nfrom the role\n")
        commit(self.root, "a.txt", "one\nfrom main\n")
        commit(self.root, "a.txt", "one\nfrom main\nfrom the role\n")  # the same work, landed with the conflict resolved
        empty = worktree(self.root, "role-empty")  # no commit of its own yet
        found = lines(self.root)
        cases = {picked: True, apart: False, conflicted: False, empty: True}
        for path, named in cases.items():
            with self.subTest(path.name):
                hits = [line for line in found if f"/{path.name} (branch {path.name})" in line]
                self.assertEqual(len(hits), 1 if named else 0, found)
                if named:
                    command = hits[0].split("`")[1]
                    self.assertTrue(
                        command.startswith("git worktree remove ") and command.endswith(f"/{path.name}"), "the note gives the command that closes it"
                    )
        self.assertEqual(len(found), 2, found)

    def test_a_worktree_on_the_branch_checked_out_counts_and_is_named_with_it(self):
        git(self.root, "checkout", "-q", "-b", "change")
        role = worktree(self.root, "role-on-change")
        sha = commit(role, "b.txt", "two\n")
        git(self.root, "cherry-pick", sha)
        (line,) = [w for w in lines(self.root) if "role-on-change" in w and "worktree" in w]
        self.assertIn("every commit on change", line)

    def test_a_branch_with_no_worktree_is_named_when_merged_or_picked_and_never_the_trunk(self):
        git(self.root, "branch", "merged")  # every commit on main by ancestry
        role = worktree(self.root, "picked")
        sha = commit(role, "b.txt", "two\n")
        git(self.root, "cherry-pick", sha)
        git(self.root, "worktree", "remove", str(role))  # the lead removed the worktree and kept the branch
        loose = worktree(self.root, "apart")
        commit(loose, "c.txt", "three\n")
        git(self.root, "worktree", "remove", str(loose))
        git(self.root, "checkout", "-q", "-b", "change")  # main is now checked out nowhere, and is never named
        found = [line for line in lines(self.root) if "the branch" in line]
        names = sorted(line.split("the branch ", 1)[1].split(" ", 1)[0] for line in found)
        self.assertEqual(names, ["merged", "picked"], found)
        for line in found:
            self.assertIn("`git branch -d ", line)

    def test_a_locked_or_missing_worktree_is_not_named(self):
        locked = worktree(self.root, "role-locked")
        git(self.root, "worktree", "lock", str(locked))
        gone = worktree(self.root, "role-gone")
        os.rename(gone, Path(self.tmp.name) / "moved-away")  # git now lists it as prunable
        self.assertEqual([line for line in lines(self.root) if "worktree" in line], [])

    def test_it_reads_only(self):
        role = worktree(self.root, "role-done")
        before = (git(self.root, "worktree", "list", "--porcelain"), git(self.root, "for-each-ref"), git(self.root, "status", "--porcelain"))
        self.assertTrue(lines(self.root))
        after = (git(self.root, "worktree", "list", "--porcelain"), git(self.root, "for-each-ref"), git(self.root, "status", "--porcelain"))
        self.assertEqual(before, after)
        self.assertTrue(role.is_dir())

    def test_fifty_worktrees_cost_one_git_call_each(self):
        for n in range(50):
            worktree(self.root, f"role-{n:02d}")
        calls = []
        real = kernel_git.run

        def counted(args, *rest, **kwargs):
            calls.append(args[0])
            return real(args, *rest, **kwargs)

        started = time.monotonic()
        with patch.object(kernel_git, "run", counted):
            found = lines(self.root)
        took = time.monotonic() - started
        self.assertEqual(len([line for line in found if "the worktree" in line]), 50)
        self.assertEqual(calls.count("cherry"), 50, "one patch match for each worktree, on the first target that holds it")
        self.assertLessEqual(len(calls), 50 + 15, calls)
        self.assertLess(took, 30, "a loaded machine still answers well within a doctor run")

    def test_aidd_doctor_gives_the_notes(self):
        worktree(self.root, "role-done")
        found = [m for level, m in doctor_checks.doctor(self.root) if m.startswith("left open:")]
        self.assertEqual(len(found), 1, found)


# Names a fetched branch or a hostile repository may give a branch or a folder. Each would run something else, or reach git as
# an option, or redraw the terminal, if a printed command held it as it is.
HOSTILE = {
    "a semicolon": "a;touch x",
    "a command substitution": "a$(touch x)",
    "a backtick": "a`touch x`",
    "a leading dash": "-x",
    "a space": "a b",
    "a quote": "a'b",
    "a double quote": 'a"b',
    "a line break": "a\ntouch x",
    "a terminal escape": "a\u001b[2Jb",
    "a direction mark": "a‮b",
}
PLAIN = ("role-done", "worktree-agent-a8ba3bce", "team/role.2_x")
# What a shell reads as more than a plain word.
METACHARACTERS = set(";&|$`'\"\\<>(){}*?[]~ ")


class NamesAreData(unittest.TestCase):
    """A branch name or a path joins a printed command only when it is a plain name, quoted, after `--`."""

    def test_a_hostile_name_gets_no_command_and_shows_on_one_line(self):
        for thing in ("worktree", "branch"):
            for label, name in HOSTILE.items():
                with self.subTest(thing=thing, name=label):
                    step = doctor_leftovers.close_step(thing, name)
                    self.assertNotIn("`", step, "no command holds a name outside the plain set")
                    self.assertNotIn(name, step)
                    shown = doctor_leftovers._shown(name)
                    self.assertNotIn("\n", shown)
                    self.assertFalse({"\u001b", "‮", "\r", "`"} & set(shown), "no part of a name reads as a command span")

    def test_a_plain_name_gets_its_command_quoted_after_a_double_dash(self):
        for thing, prefix in (("worktree", "git worktree remove -- "), ("branch", "git branch -d -- ")):
            for name in PLAIN:
                with self.subTest(thing=thing, name=name):
                    step = doctor_leftovers.close_step(thing, name)
                    self.assertEqual(step, f"`{prefix}{name}`")

    def test_a_hostile_branch_and_folder_in_a_repository_print_no_command_and_no_extra_line(self):
        with tempfile.TemporaryDirectory() as d:
            root = repository(Path(d))
            branches = [n for n in HOSTILE.values() if git_allows(root, n)]
            self.assertGreaterEqual(len(branches), 3, "git allows some hostile names, so the case is real")
            for n, name in enumerate(HOSTILE.values()):
                path = Path(d) / f"wt{n}-{name.replace('/', '_')}"
                git(root, "worktree", "add", "-q", "-b", f"wt{n}", str(path))
            found = doctor_leftovers.leftover_lines(root)
        notes = [m for _, m in found]
        self.assertEqual(len(notes), len(HOSTILE) + len(branches), notes)
        for note in notes:
            with self.subTest(note=note):
                self.assertNotIn("\n", note)
                self.assertFalse({"\u001b", "‮"} & set(note))
                commands = note.split("`")[1::2]
                for command in commands:
                    self.assertIn(" -- ", command, "every value comes after `--`")
                    self.assertFalse(METACHARACTERS & set(command.split(" -- ", 1)[1]), command)


def git_allows(root: Path, name: str) -> bool:
    """Make a branch `name` when git takes the name, and say whether it did."""
    import subprocess

    return subprocess.run(["git", "branch", "--", name], cwd=root, capture_output=True).returncode == 0


class LeftOpenScratchFolders(unittest.TestCase):
    def test_a_scratch_folder_past_its_age_is_named_and_no_other(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            tmp = root / ".aidd" / "tmp"
            now = time.time()
            day = 86400
            cases = {  # name -> (days since the folder changed, days since its newest entry changed, named)
                "t.old": (10, 10, True),
                "t.edge": (7, 7, True),
                "t.young": (6, 6, False),
                "t.old-with-a-new-file": (10, 1, False),
                "t.new": (0, 0, False),
            }
            for name, (folder_age, entry_age, _) in cases.items():
                (tmp / name).mkdir(parents=True)
                entry = tmp / name / "log.txt"
                entry.write_text("x", encoding="utf-8")
                os.utime(entry, (now - entry_age * day, now - entry_age * day))
                os.utime(tmp / name, (now - folder_age * day, now - folder_age * day))
            (tmp / "a-file").write_text("x", encoding="utf-8")
            os.utime(tmp / "a-file", (now - 30 * day, now - 30 * day))
            os.symlink(tmp / "t.old", tmp / "a-link")
            found = doctor_leftovers.scratch_lines(root, now=now)
            for name, (_, _, named) in cases.items():
                with self.subTest(name):
                    hits = [m for _, m in found if f".aidd/tmp/{name} " in m]
                    self.assertEqual(len(hits), 1 if named else 0, found)
                    if named:
                        self.assertNotIn("`", hits[0], "a role never deletes a scratch folder, so doctor prints no command for it")
            self.assertEqual(len(found), 2, found)

    def test_no_scratch_folder_or_a_link_in_its_place_says_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            root.mkdir()
            self.assertEqual(doctor_leftovers.scratch_lines(root), [])
            (Path(d) / "elsewhere" / "t.old").mkdir(parents=True)
            (root / ".aidd").mkdir()
            os.symlink(Path(d) / "elsewhere", root / ".aidd" / "tmp")
            self.assertEqual(doctor_leftovers.scratch_lines(root, now=time.time() + 30 * 86400), [])


if __name__ == "__main__":
    unittest.main()
