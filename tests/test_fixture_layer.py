"""The shared reads of the fixture layer (`shared_reads.shared_git_reads`, `shared_reads.ReadOnlyRepoCase`) never change an answer.

Invariant: for every command line and every rule set, aidd's answer inside a shared-reads block over a repository whose refs
and config do not change is the answer outside it, and a block or a class whose repository's refs, HEAD, or config change
fails, because every later row would read the old state.
"""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
import shared_reads

from aidd import config, risk
from aidd.kernel import git as kernel_git
from aidd.kernel import git_reads

ENVIRONMENTS = 'aidd_version: "1.0.0"\nprofile: solo\nenvironments:\n  - {name: production, branches: [prod], tags: ["v*"]}\n  - {name: dev, branches: [dev], shared: false}\n'
LINES = (
    "git push",
    "git push origin feat",
    "git push origin main",
    "git push origin prod",
    "git push origin HEAD:prod",
    "git push origin v1",
    "git push --tags origin",
    "git push --delete origin dev",
    "git switch main && git push",
    "git status",
    "",
)


def build(root: str) -> None:
    """A repository on `feat` with a commit, tags, a remote, and the branches the lines name."""
    helpers.git(root, "init", "-q", "-b", "main")
    helpers.git(root, "commit", "-q", "--allow-empty", "-m", "base")
    helpers.git(root, "tag", "v1")
    helpers.git(root, "remote", "add", "origin", "https://example.invalid/origin.git")
    helpers.git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    for branch in ("prod", "dev"):
        helpers.git(root, "branch", branch)
    helpers.git(root, "switch", "-qc", "feat")


class TheAnswerIsTheSameInsideAndOutside(unittest.TestCase):
    def test_every_line_under_each_rule_set_reads_the_same_in_a_shared_block(self):
        rule_sets = {"no config": risk.rule_set(None), "environments": risk.rule_set(config.load_text(ENVIRONMENTS))}
        with tempfile.TemporaryDirectory() as tmp:
            root = str(Path(tmp).resolve())
            build(root)
            outside = {(name, line): risk.command_level(rs, line, cwd=root) for name, rs in rule_sets.items() for line in LINES}
            with shared_reads.shared_git_reads(root):
                inside = {(name, line): risk.command_level(rs, line, cwd=root) for name, rs in rule_sets.items() for line in LINES}
        for key, answer in outside.items():
            with self.subTest(rule_set=key[0], line=key[1]):
                self.assertEqual(inside[key], answer)


class AWriteInsideABlockFailsIt(unittest.TestCase):
    def test_a_ref_a_branch_a_setting_or_the_checked_out_branch_changed_inside_fails_the_block(self):
        writes = {
            "a tag": ("tag", "later"),
            "a branch": ("branch", "other"),
            "a setting": ("config", "--local", "push.default", "upstream"),
            "the checked out branch": ("switch", "-q", "main"),
            "a ref": ("update-ref", "refs/remotes/origin/feat", "HEAD"),
        }
        for name, args in writes.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                root = str(Path(tmp).resolve())
                build(root)
                with self.assertRaises(AssertionError) as caught, shared_reads.shared_git_reads(root):
                    helpers.git(root, *args)
                self.assertIn("changed inside shared_git_reads", str(caught.exception))

    def test_a_block_with_no_write_passes_and_ends_the_sharing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = str(Path(tmp).resolve())
            build(root)
            with shared_reads.shared_git_reads(root):
                self.assertIsNotNone(git_reads.current())
            self.assertIsNone(git_reads.current())

    def test_a_kept_read_is_stale_after_a_write_which_is_why_the_block_refuses_the_read(self):
        """The relation can fail: in a bare scope the checked out branch is read once, so a later switch is not seen; the block
        refuses that read, so no row is answered by it."""
        with tempfile.TemporaryDirectory() as tmp:
            root = str(Path(tmp).resolve())
            build(root)
            seen = []
            with git_reads.shared_reads():
                seen.append(kernel_git.current_branch(root))
                helpers.git(root, "switch", "-q", "main")
                seen.append(kernel_git.current_branch(root))
            self.assertEqual(seen, ["feat", "feat"], "the control: the read inside a bare scope is the kept one")
            helpers.git(root, "switch", "-q", "feat")
            seen.clear()
            with self.assertRaises(AssertionError), shared_reads.shared_git_reads(root):
                seen.append(kernel_git.current_branch(root))
                helpers.git(root, "switch", "-q", "main")
                seen.append(kernel_git.current_branch(root))
            self.assertEqual(seen, ["feat"], "the block refused the second read")
            self.assertEqual(kernel_git.current_branch(root), "main", "outside the block the read is fresh")


class AReadOnlyClassFailsATestThatWrites(unittest.TestCase):
    def run_class(self, writes: bool) -> unittest.TestResult:
        class Fixture(shared_reads.ReadOnlyRepoCase):
            @classmethod
            def setUpClass(cls):
                super().setUpClass()
                cls.tmp = tempfile.TemporaryDirectory()
                cls.addClassCleanup(cls.tmp.cleanup)
                cls.root = str(Path(cls.tmp.name).resolve())
                build(cls.root)
                cls.share_reads()

            def test_a_reads(self):
                self.assertEqual(kernel_git.current_branch(self.root), "feat")

            def test_b_changes_the_repository(self):
                if writes:
                    helpers.git(self.root, "tag", "written")

        result = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromTestCase(Fixture))
        self.assertIsNone(git_reads.current(), "the class's cleanup ends the sharing")
        return result

    def test_only_a_test_that_changes_the_repository_fails(self):
        clean = self.run_class(writes=False)
        self.assertEqual((clean.testsRun, len(clean.failures), len(clean.errors)), (2, 0, 0))
        dirty = self.run_class(writes=True)
        failed = [test.id().rsplit(".", 1)[-1] for test, _ in dirty.failures + dirty.errors]
        self.assertIn("test_b_changes_the_repository", failed)
        self.assertNotIn("test_a_reads", failed)


class AWriteThatIsUndoneBeforeTheEndIsStillCaught(unittest.TestCase):
    """The guard compares the refs at each git call aidd makes, so a read between a write and its undo fails, though the
    state at the end equals the state at the start."""

    def test_a_block_fails_at_the_read_that_a_write_it_later_undoes_would_have_staled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = str(Path(tmp).resolve())
            build(root)
            seen = []
            with self.assertRaises(AssertionError) as caught, shared_reads.shared_git_reads(root):
                seen.append(kernel_git.current_branch(root))
                helpers.git(root, "switch", "-q", "main")
                try:
                    kernel_git.current_branch(root)
                finally:
                    helpers.git(root, "switch", "-q", "feat")
            self.assertEqual(seen, ["feat"])
            self.assertIn("changed inside shared_git_reads before", str(caught.exception))
            self.assertEqual(kernel_git.current_branch(root), "feat")

    def test_a_block_whose_write_is_undone_with_no_read_between_is_the_state_it_started_in(self):
        """The control: a write and its undo that no read sees changes no answer, so the block passes."""
        with tempfile.TemporaryDirectory() as tmp:
            root = str(Path(tmp).resolve())
            build(root)
            with shared_reads.shared_git_reads(root):
                before = kernel_git.current_branch(root)
                helpers.git(root, "switch", "-q", "main")
                helpers.git(root, "switch", "-q", "feat")
                self.assertEqual(kernel_git.current_branch(root), before)

    def test_the_global_config_an_included_file_and_an_object_no_ref_names_are_watched_too(self):
        """What a kept read can come from beyond the repository's own refs and config: each write is seen at the next git call."""
        with tempfile.TemporaryDirectory() as tmp:
            outer = Path(tmp).resolve()
            glob_file, extra = outer / "global.gitconfig", outer / "extra.gitconfig"
            glob_file.write_text("[user]\n\tname = one\n", encoding="utf-8")
            extra.write_text("[user]\n\temail = one@example.com\n", encoding="utf-8")
            writers = {
                "the global config": lambda root: glob_file.write_text("[user]\n\tname = two\n", encoding="utf-8"),
                "a file the config includes": lambda root: extra.write_text("[user]\n\temail = two@example.com\n", encoding="utf-8"),
                "an object no ref names": lambda root: subprocess.run(
                    ["git", "hash-object", "-w", "--stdin"], cwd=root, input=b"new", check=True, capture_output=True
                ),
            }
            for name, write in writers.items():
                with self.subTest(name), mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(glob_file)}):
                    root = str(outer / name.replace(" ", "-"))
                    Path(root).mkdir()
                    build(root)
                    helpers.git(root, "config", "--local", "include.path", str(extra))
                    with self.assertRaises(AssertionError) as caught, shared_reads.shared_git_reads(root):
                        kernel_git.current_branch(root)
                        write(root)
                        kernel_git.current_branch(root)
                    self.assertIn("changed inside shared_git_reads before", str(caught.exception))

    def run_class(self, undone: bool) -> unittest.TestResult:
        class Fixture(shared_reads.ReadOnlyRepoCase):
            @classmethod
            def setUpClass(cls):
                super().setUpClass()
                cls.tmp = tempfile.TemporaryDirectory()
                cls.addClassCleanup(cls.tmp.cleanup)
                cls.root = str(Path(cls.tmp.name).resolve())
                build(cls.root)
                cls.share_reads()

            def test_reads_between_a_write_and_its_undo(self):
                if undone:
                    helpers.git(self.root, "switch", "-q", "main")
                kernel_git.current_branch(self.root)
                if undone:
                    helpers.git(self.root, "switch", "-q", "feat")

        return unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromTestCase(Fixture))

    def test_a_class_test_that_reads_between_a_write_and_its_undo_fails(self):
        clean, undone = self.run_class(undone=False), self.run_class(undone=True)
        self.assertEqual((clean.testsRun, len(clean.failures), len(clean.errors)), (1, 0, 0))
        failed = [test.id().rsplit(".", 1)[-1] for test, _ in undone.failures + undone.errors]
        self.assertIn("test_reads_between_a_write_and_its_undo", failed)


class ACopiedTemplateStartsCleanForEveryTest(unittest.TestCase):
    """Invariant: every test of a `RepoTemplateCase` class starts from the files the template was built with, whatever an
    earlier test wrote or removed in its own copy, in whatever order the tests run."""

    def run_class(self, order: tuple[str, ...]) -> unittest.TestResult:
        class Fixture(helpers.RepoTemplateCase):
            @classmethod
            def build_template(cls, root):
                (root / "kept.txt").write_text("template\n", encoding="utf-8")

            def test_writes_and_removes(self):
                (self.root / "kept.txt").write_text("changed\n", encoding="utf-8")
                (self.root / "added.txt").write_text("new\n", encoding="utf-8")

            def test_deletes(self):
                (self.root / "kept.txt").unlink()

            def test_starts_clean(self):
                self.assertEqual((self.root / "kept.txt").read_text(encoding="utf-8"), "template\n")
                self.assertFalse((self.root / "added.txt").exists())

        suite = unittest.TestSuite(Fixture(name) for name in order)
        return unittest.TextTestRunner(stream=io.StringIO()).run(suite)

    def test_a_test_never_sees_what_another_wrote(self):
        names = ("test_writes_and_removes", "test_deletes", "test_starts_clean")
        for order in (names, names[::-1], (names[1], names[2], names[0])):
            with self.subTest(order=order):
                result = self.run_class(order)
                self.assertEqual((result.testsRun, len(result.failures), len(result.errors)), (3, 0, 0))


if __name__ == "__main__":
    unittest.main()
