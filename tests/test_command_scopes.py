"""`aidd status`, `aidd validate`, and `aidd risk` read each ref and setting once, and answer as they did when each read ran again.

Invariant: for every command line below, in every repository state below, the exit code, the output, and the error text are those of the
same command with no scope open, where each git read runs every time it is asked (`git_reads.current` gives None, so `kernel.git` keeps
nothing). A scope lasts one command: a repository that changes between two commands is read again by the second. The cost is counted in git
processes, never timed.
"""

from __future__ import annotations

import random
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers

from aidd.kernel import git as kernel_git
from aidd.kernel import git_reads

# Each command line, with the repository it is asked in.
COMMANDS = (
    ("status",),
    ("status", "--all-branches", "--json"),
    ("status", "SPEC-220", "--json"),
    ("status", "src/checkout/cart.py", "--json"),
    ("validate",),
    ("risk", "--paths", "src/a.py", "docs/b.md", "tests/c.py"),
    ("risk", "--paths", "src/checkout/cart.py", "--change-type", "fix", "--json"),
    ("risk", "--command", "git push --force origin feat", "--json"),
    ("init", "--dry-run", "--force", "--profile", "solo", "--harness", "claude-code"),
    ("risk", "--paths"),  # a usage error is the same error
    ("status", "NO-SUCH-ID"),
)


def asked(root: str, argv: tuple[str, ...], *, scoped: bool) -> tuple[int, str, str]:
    """The exit code, stdout, and stderr of `aidd <argv>` in `root`, with the scope the command opens or with none at all."""
    kernel_git._empty_tree.cache_clear()
    if scoped:
        done = helpers.aidd_here(*argv, cwd=root)
    else:
        with mock.patch.object(git_reads, "current", return_value=None):
            done = helpers.aidd_here(*argv, cwd=root)
    return done.returncode, done.stdout, done.stderr


def git_processes(root: str, argv: tuple[str, ...], *, scoped: bool) -> int:
    class Counter(subprocess.Popen):
        started = 0

        def __init__(self, args, *rest, **kwargs):
            if isinstance(args, (list, tuple)) and args and Path(str(args[0])).name == "git":
                Counter.started += 1
            super().__init__(args, *rest, **kwargs)

    with mock.patch.object(subprocess, "Popen", Counter):
        asked(root, argv, scoped=scoped)
    return Counter.started


class RepositoryCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = str(helpers.make_repo(Path(cls.tmp.name).resolve() / "repo", spec="specs/SPEC-220.md", status="approved"))
        # A work tree with a committed Spec on a feature branch, a second branch, an untracked file, and a dirty tracked one.
        helpers.git(cls.root, "add", "-A")
        helpers.git(cls.root, "-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-qm", "SPEC-220: the Spec")
        helpers.git(cls.root, "branch", "other", "main")
        Path(cls.root, "src", "checkout").mkdir(parents=True, exist_ok=True)
        Path(cls.root, "src", "checkout", "cart.py").write_text("x = 1\n", encoding="utf-8")
        Path(cls.root, "notes.txt").write_text("scratch\n", encoding="utf-8")


class ACommandInAScopeAnswersAsWithNoScopeTests(RepositoryCase):
    def test_every_command_gives_the_answer_it_gave_with_no_scope_and_leaves_none_open(self):
        for argv in COMMANDS:
            with self.subTest(command=" ".join(argv)):
                self.assertEqual(asked(self.root, argv, scoped=True), asked(self.root, argv, scoped=False))
                self.assertIsNone(git_reads.current(), "a scope outlived its command")

    def test_the_table_reaches_every_kind_of_answer(self):
        """The control: the commands are not all errors, and some print, so the comparison can differ."""
        codes = {argv: asked(self.root, argv, scoped=False)[0] for argv in COMMANDS}
        self.assertIn(0, codes.values())
        self.assertIn(2, codes.values())
        self.assertTrue(all(asked(self.root, argv, scoped=False)[1] for argv in COMMANDS if codes[argv] == 0))


PATH_POOL = (
    "src/a.py",
    "src/auth/login.py",
    "src/payments/refund.py",
    "db/migrations/001_init.sql",
    ".github/workflows/ci.yml",
    "docs/guide.md",
    "README.md",
    "tests/test_a.py",
    "package.json",
    ".env",
    "specs/SPEC-220.md",
    ".aidd/config.yaml",
    "src/checkout/cart.py",
    "infra/main.tf",
    "src/**/*.py",
    "a b/c d.txt",
)


def generated_paths(count: int = 6) -> list[tuple[str, ...]]:
    """Lists of one to four planned paths, drawn from every kind of area, by a fixed seed."""
    rng = random.Random(20261113)
    return [tuple(rng.sample(PATH_POOL, rng.randint(1, 4))) for _ in range(count)]


class ThePathsRouteIsTheSameInAScopeOnEveryBranchTests(RepositoryCase):
    def test_a_generated_set_of_planned_paths_routes_as_it_did_with_no_scope(self):
        for branch in ("feat", "main"):
            helpers.git(self.root, "checkout", "-q", branch)
            self.addCleanup(helpers.git, self.root, "checkout", "-q", "feat")
            for paths in generated_paths():
                argv = ("risk", "--paths", *paths, "--json")
                with self.subTest(branch=branch, paths=paths):
                    scoped = asked(self.root, argv, scoped=True)
                    self.assertEqual(scoped[0], 0)
                    self.assertEqual(scoped, asked(self.root, argv, scoped=False))


class AScopeLastsOneCommandTests(RepositoryCase):
    def test_a_repository_that_changed_between_two_commands_is_read_again(self):
        before = asked(self.root, ("status", "--json"), scoped=True)
        self.addCleanup(helpers.git, self.root, "checkout", "-q", "feat")
        helpers.git(self.root, "checkout", "-q", "other")
        after = asked(self.root, ("status", "--json"), scoped=True)
        self.assertNotEqual(before, after, "the control: moving the branch changes the answer")
        self.assertEqual(after, asked(self.root, ("status", "--json"), scoped=False))


class ACommandStartsFewerGitProcessesInAScopeTests(RepositoryCase):
    def test_a_command_in_a_scope_starts_fewer_git_processes(self):
        for argv in (("status",), ("validate",), ("risk", "--paths", "src/a.py", "docs/b.md", "tests/c.py"), ("init", "--dry-run", "--profile", "team")):
            with self.subTest(command=" ".join(argv)):
                with_scope, without = git_processes(self.root, argv, scoped=True), git_processes(self.root, argv, scoped=False)
                self.assertLess(with_scope, without)


if __name__ == "__main__":
    unittest.main()
