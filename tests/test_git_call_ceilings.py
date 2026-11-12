"""A command a person runs starts git a bounded number of times, so the cost of its reads cannot creep back.

Each ceiling is a count of git processes, never seconds: the count is the same on a loaded machine and a quiet one. A ceiling
is the measured count with room for a read a change adds on purpose; a change that adds many reads raises what a person
waits for, so it raises a ceiling only with its reason beside the new number.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
from product_scope_fixtures import PERSON, ScopeCase, objective, outcome, prd, text

from aidd.kernel import git as kernel_git
from aidd.workitems import approval_commits, product_approval

# The command, and the most git processes it may start in an adopted repository of the fixture's size.
CEILINGS = (
    (("risk", "--paths", "src/a.py", "docs/b.md", "tests/c.py"), 7),
    (("status",), 16),
    (("validate",), 20),
    (("doctor", "--json"), 18),
    (("init", "--dry-run"), 16),
)


class Counter(subprocess.Popen):
    started = 0

    def __init__(self, args, *rest, **kwargs):
        if isinstance(args, (list, tuple)) and args and Path(str(args[0])).name == "git":
            Counter.started += 1
        super().__init__(args, *rest, **kwargs)


def git_processes(root: str, argv: tuple[str, ...]) -> int:
    """How many git processes `aidd <argv>` starts, as a fresh process would: with no probe answered by an earlier command."""
    kernel_git._empty_tree.cache_clear()
    kernel_git._version_seen.clear()
    Counter.started = 0
    with mock.patch.object(subprocess, "Popen", Counter):
        helpers.aidd_here(*argv, cwd=root)
    return Counter.started


class ACommandStartsGitABoundedNumberOfTimes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = str(helpers.make_repo(Path(cls.tmp.name).resolve() / "repo"))

    def test_no_command_starts_more_git_processes_than_its_ceiling(self):
        for argv, ceiling in CEILINGS:
            with self.subTest(command=" ".join(argv)):
                started = git_processes(self.root, argv)
                self.assertGreater(started, 0, "the control: the counter sees the command's git processes")
                self.assertLessEqual(started, ceiling, f"`aidd {' '.join(argv)}` started {started} git processes, over its ceiling of {ceiling}")

    def test_a_command_started_twice_starts_the_same_number_both_times(self):
        """The control: the count is the command's own, not what an earlier command left cached in this process."""
        for argv, _ in CEILINGS:
            with self.subTest(command=" ".join(argv)):
                self.assertEqual(git_processes(self.root, argv), git_processes(self.root, argv))


class TheLastApprovalOfALongHistoryStartsGitInProportionToIt(ScopeCase):
    """The search for a file's last approval reads each commit once and looks up each stamp once: a stamp that no commit records,
    kept through many commits, costs one lookup and not one for each commit."""

    UNSTAMPED, STAMPED = 10, 30

    def test_the_count_of_git_processes_is_a_few_for_each_commit_and_no_more(self):
        outs = [outcome(1, serves="Objective-1")]
        for n in range(self.UNSTAMPED):
            self.write("product/prd.md", text(prd(outs, objectives=[objective()]), f"\n## Users\n\nDraft {n}.\n"))
            self.commit(f"draft {n}")
        for n in range(self.STAMPED):
            stamped = prd(outs, objectives=[objective()], approved_by=PERSON, approved_at="2027-01-10T09:00:00Z")
            self.write("product/prd.md", text(stamped, f"\n## Users\n\nLater {n}.\n"))
            self.commit(f"edit {n}")
        commits = self.UNSTAMPED + self.STAMPED
        approval_commits.FILE_TEXTS.clear()
        Counter.started = 0
        with mock.patch.object(subprocess, "Popen", Counter):
            found = product_approval.last_approved_text(self.root, "product/prd.md")
        self.assertIsNone(found, "no commit records the stamp, so no approval stands")
        self.assertGreater(Counter.started, commits, "the control: every commit's file is read")
        self.assertLessEqual(Counter.started, 2 * commits + 10, f"{Counter.started} git processes for {commits} commits")


if __name__ == "__main__":
    unittest.main()
