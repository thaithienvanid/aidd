"""R426: a `git checkout` or `git switch` earlier on a line, read beside the session's branch for a later merge or push.

Its own file beside test_local_merge.py, because its table reads each line from three branches and runs git for each."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import helpers
from aidd import risk


def answer(line: str, cwd: str) -> tuple[str, list[tuple[str, str | None]]]:
    a = risk.command_level(risk.rule_set(None), line, cwd=cwd)
    return a["level"], [(x["action"], x["branch"]) for x in a["actions"]]


class ACheckoutEarlierOnTheLineOnlyAddsAStricterRead(unittest.TestCase):
    """R426 and its security review: a `git checkout` or `git switch` before a merge or a push of the branch checked
    out adds the branch it names to read beside the session's, and the stricter reading wins. A checkout may fail or run
    unwaited (`;`, `||`, `&`, a new line, `if !`), so it never lowers a level. A branch the line creates is one's own, an
    existing one shared, and a name aidd cannot read the default branch. Redirections are no paths, a wrapped command is
    read call by call, a checkout of files after `--` moves nothing, and a push that names its branch keeps its reading.

    Each row is read from main, from a feature branch (feat, tracking origin/feat), and from a repository with no
    default branch git can tell (on trunk): first the level now, then the level at f2b5f4e, before checkouts were read,
    which it never goes under."""

    ROWS = [
        ("git checkout main && git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git checkout -q main && git merge --no-ff feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git switch main; git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git switch main || git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git checkout main & git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git checkout main\ngit merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("if ! git checkout main; then git merge feat; fi", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git checkout main 2>&1 && git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git checkout main >/dev/null 2>/dev/null && git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git checkout main >&2 && git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git checkout main <notes.txt && git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("bash -c 'git checkout main && git merge feat'", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("sh -c 'git switch main; git merge feat'", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("env GIT_TRACE=0 git checkout main && git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("(git checkout main) && git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git checkout main -- && git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git checkout -B main && git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git checkout main && git push", "ask", "ask", "ask", "ask", "allow", "allow"),
        ("git checkout main && git push origin HEAD", "ask", "ask", "ask", "ask", "allow", "allow"),
        ("git checkout main && git push origin HEAD:main", "ask", "ask", "ask", "ask", "ask", "ask"),
        ("git checkout main && git push origin feat", "ask", "allow", "ask", "ask", "allow", "ask"),
        ("git checkout -b new && git merge feat", "ask", "allow", "ask", "ask", "allow", "ask"),
        ("git checkout -b new; git merge feat", "ask", "allow", "ask", "ask", "allow", "ask"),
        ("git checkout -b new || git merge feat", "ask", "allow", "ask", "ask", "allow", "ask"),
        ("git checkout -b new & git merge feat", "ask", "allow", "ask", "ask", "allow", "ask"),
        ("git checkout -b new\ngit merge feat", "ask", "allow", "ask", "ask", "allow", "ask"),
        ("if ! git checkout -b new; then git merge feat; fi", "ask", "allow", "ask", "ask", "allow", "ask"),
        ("git switch -c new && git push", "ask", "allow", "ask", "ask", "allow", "allow"),
        ("git switch -c new && git push -u origin new", "ask", "ask", "ask", "ask", "ask", "ask"),
        ("git switch --create=new && git merge feat", "ask", "allow", "ask", "ask", "allow", "ask"),
        ("git checkout --orphan new && git merge feat", "ask", "allow", "ask", "ask", "allow", "ask"),
        ("git checkout -- notes.txt && git merge feat", "ask", "allow", "ask", "ask", "allow", "ask"),
        ("git checkout main -- notes.txt && git merge feat", "ask", "allow", "ask", "ask", "allow", "ask"),
        ("git checkout notes.txt && git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git checkout feat && git merge main", "ask", "allow", "ask", "allow", "allow", "ask"),
        ("git merge feat && git checkout main", "ask", "allow", "ask", "ask", "allow", "ask"),
        ("git checkout other && git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git checkout other && git push", "ask", "ask", "ask", "ask", "allow", "allow"),
        ("git checkout - && git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git checkout @{-1} && git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git checkout v1 && git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git checkout origin/feat && git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git checkout --detach && git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git switch --track origin/theirs && git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git checkout $BRANCH && git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git checkout $(git rev-parse main) && git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git checkout -b other && git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git -C ../x checkout main && git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git checkout -b new && cd sub && git merge feat", "ask", "ask", "ask", "ask", "allow", "ask"),
        ("git checkout main && git merge origin/feat", "ask", "ask", "ask", "ask", "allow", "ask"),
    ]

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name).resolve()
        cls.repos = {"main": cls.repo(base / "repo", "main"), "trunk": cls.repo(base / "trunk", "trunk")}
        repo = cls.repos["main"]
        helpers.git(repo, "remote", "add", "origin", "https://example.invalid/origin.git")
        for branch in ("main", "feat", "other", "theirs"):
            helpers.git(repo, "update-ref", f"refs/remotes/origin/{branch}", "HEAD")
        for branch in ("main", "feat", "other"):
            helpers.git(repo, "branch", "-q", "-u", f"origin/{branch}", branch)

    @staticmethod
    def repo(root: Path, first: str) -> str:
        root.mkdir()
        helpers.git(str(root), "init", "-q", "-b", first)
        Path(root, "notes.txt").write_text("x\n", encoding="utf-8")
        Path(root, "sub").mkdir()
        Path(root, "sub", "keep.txt").write_text("x\n", encoding="utf-8")
        helpers.git(str(root), "add", "-A")
        helpers.git(str(root), "commit", "-q", "-m", "base")
        helpers.git(str(root), "tag", "v1")
        for branch in ("feat", "other"):
            helpers.git(str(root), "branch", branch)
        return str(root)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_each_line_from_each_branch_is_never_looser_than_before(self):
        rank = {"allow": 0, "report": 1, "ask": 2}
        for here, repo, column in (("main", self.repos["main"], 1), ("feat", self.repos["main"], 2), ("trunk", self.repos["trunk"], 3)):
            helpers.git(repo, "switch", "-q", here)
            for row in self.ROWS:
                line, now, before = row[0], row[column], row[column + 3]
                with self.subTest(here=here, line=line):
                    self.assertGreaterEqual(rank[now], rank[before], "a checkout never lowers a level")
                    self.assertEqual(answer(line, repo)[0], now)

    def test_a_checkout_the_line_names_reads_as_the_rule_names_it(self):
        helpers.git(self.repos["main"], "switch", "-q", "feat")
        cases = [
            ("git checkout main && git merge main~0", ("ask", [("git.merge", "default")])),
            ("git checkout -b new && git merge main", ("allow", [("git.merge", "own")])),
            ("git checkout other && git merge main", ("ask", [("git.merge", "shared")])),
            ("git checkout v1 && git merge main", ("ask", [("git.merge", "default")])),
            ("git checkout main && git push origin feat", ("allow", [("git.push", "own")])),
        ]
        for line, want in cases:
            with self.subTest(line=line):
                self.assertEqual(answer(line, self.repos["main"]), want)

    def test_the_cli_reads_the_branch_the_line_checks_out(self):
        helpers.git(self.repos["main"], "switch", "-q", "feat")
        done = helpers.aidd_subprocess("risk", "--command", "git checkout -q main && git merge --no-ff feat", "--json", cwd=self.repos["main"])
        self.assertEqual(json.loads(done.stdout)["level"], "ask", done.stderr)


if __name__ == "__main__":
    unittest.main()
