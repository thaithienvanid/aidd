"""`aidd list` stays fast on a busy repository: a day of agents leaves dozens of finished Task and fix branches, and
the list must not read each one. A branch the default branch holds, or whose work another open branch holds, costs no
git call of its own; the trunk-flow count names the open work once."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import git, make_repo

from aidd import workitems
from aidd.cli import main
from aidd.kernel import git as kernel_git


def spec_on(root: Path, branch: str, sid: str, base: str = "main") -> None:
    git(root, "switch", "-qc", branch, base)
    (root / "specs" / f"{sid}.md").write_text(
        f'---\naidd_version: "1.0.0"\nkind: spec\nid: {sid}\nstatus: draft\n\ntasks:\n  - id: {sid}-T1\n    scope: ["app/{sid}/**"]\n---\n',
        encoding="utf-8",
    )
    git(root, "add", "-A")
    git(root, "commit", "-qm", sid)


class ListSpeedTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_repo(Path(tmp.name).resolve() / "repo", "solo", approvers=["email:me@example.com"], branch=None)
        spec_on(self.root, "spec/SPEC-1", "SPEC-1")

    def finished_branches(self, n: int) -> None:
        """`n` Task branches merged into spec/SPEC-1, and `n` fix branches the default branch holds."""
        for i in range(n):
            git(self.root, "switch", "-qc", f"task/SPEC-1-T{i}", "spec/SPEC-1")
            git(self.root, "commit", "-q", "--allow-empty", "-m", f"task {i}")
            git(self.root, "switch", "-q", "spec/SPEC-1")
            git(self.root, "merge", "-q", "--no-ff", "-m", f"merge task {i}", f"task/SPEC-1-T{i}")
            git(self.root, "branch", f"fix/old-{i}", "main")

    def git_calls(self, *args: str) -> int:
        real, calls = kernel_git.subprocess.run, []

        def counting(cmd, *a, **k):
            calls.append(cmd)
            return real(cmd, *a, **k)

        with mock.patch.object(kernel_git.subprocess, "run", counting), contextlib.chdir(self.root), contextlib.redirect_stdout(io.StringIO()):
            with contextlib.suppress(SystemExit):
                main(list(args))
        return sum(1 for c in calls if isinstance(c, list) and c[:1] == ["git"])

    def test_a_task_branch_merged_into_its_spec_branch_is_that_branchs_work(self):
        self.finished_branches(3)
        spec_on(self.root, "spec/SPEC-2", "SPEC-2")
        self.assertEqual(sorted(b["branch"] for b in workitems.work_branches(str(self.root))), ["spec/SPEC-1", "spec/SPEC-2"])

    def test_finished_branches_cost_no_git_call_of_their_own(self):
        views = (["list", "--json"], ["list", "--branch", "--json"])
        before = [self.git_calls(*args) for args in views]
        self.finished_branches(12)
        after = [self.git_calls(*args) for args in views]
        for args, b, a in zip(views, before, after, strict=True):
            with self.subTest(args=args):
                self.assertLessEqual(a - b, 4, f"{b} git calls, then {a} with 24 more finished branches")


if __name__ == "__main__":
    unittest.main()
