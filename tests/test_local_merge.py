"""A local `git merge` into the default branch is `git.merge`, which asks. The branch comes from git, as a push's does:
on any other branch the merge is `own`, which allows. A merge that lands no other work, such as `--abort` or the
branch's own upstream, is no merge at all. A harness rule cannot see the branch, so the harness rules hold no
`git merge` pattern while a merge into one's own branch is allowed."""

from __future__ import annotations

import dataclasses
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
import shared_reads
from aidd import risk
from aidd.risk import harness_rules
from aidd.risk.rules import Rule


def answer(line: str, cwd: str, rs=None) -> tuple[str, list[tuple[str, str | None]]]:
    a = risk.command_level(rs or risk.rule_set(None), line, cwd=cwd)
    return a["level"], [(x["action"], x["branch"]) for x in a["actions"]]


class ALocalMergeIntoTheDefaultBranchAsks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = cls.tmp.name
        helpers.git(cls.repo, "init", "-q", "-b", "main")
        helpers.git(cls.repo, "commit", "-q", "--allow-empty", "-m", "base")
        helpers.git(cls.repo, "branch", "feat")
        # Each branch tracks its own on origin; a second remote holds branches of the same names that it does not track.
        for remote in ("origin", "upstream"):
            helpers.git(cls.repo, "remote", "add", remote, f"https://example.invalid/{remote}.git")
            for branch in ("main", "feat"):
                helpers.git(cls.repo, "update-ref", f"refs/remotes/{remote}/{branch}", "HEAD")
        for branch in ("main", "feat"):
            helpers.git(cls.repo, "branch", "-q", "-u", f"origin/{branch}", branch)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def on(self, branch: str) -> None:
        helpers.git(self.repo, "switch", "-q", branch)

    def reading(self):
        """The block in which aidd reads each ref and setting once; switch branches before it, never inside it."""
        return shared_reads.shared_git_reads(self.repo)

    # `{other}` is the branch not checked out, and `{here}` the one checked out.
    LANDS = [
        "git merge {other}",
        "git merge --ff-only {other}",
        "git merge --no-ff -m merged {other}",
        "git merge origin/{other}",
        "git merge {here} {other}",
        "git merge --continue",
    ]
    LANDS_NOTHING = [
        "git merge --abort",
        "git merge --quit",
        "git merge",  # the branch's own upstream
        "git merge origin/{here}",
        "git merge refs/remotes/origin/{here}",
        "git merge-base {here} {other}",
    ]
    WHERE = {"main": ("feat", "ask", "default"), "feat": ("main", "allow", "own")}

    def test_a_merge_that_lands_work_asks_on_the_default_branch_only(self):
        for here, (other, level, branch) in self.WHERE.items():
            self.on(here)
            with self.reading():
                for line in self.LANDS:
                    line = line.format(here=here, other=other)
                    with self.subTest(here=here, line=line):
                        self.assertEqual(answer(line, self.repo), (level, [("git.merge", branch)]))

    def test_a_merge_that_lands_no_other_work_is_no_merge(self):
        for here, (other, _, _) in self.WHERE.items():
            self.on(here)
            with self.reading():
                for line in self.LANDS_NOTHING:
                    line = line.format(here=here, other=other)
                    with self.subTest(here=here, line=line):
                        self.assertEqual(answer(line, self.repo), ("allow", []))

    def test_review_cases_ask_where_aidd_cannot_be_sure(self):
        """An end flag only as the one argument, the configured upstream only, and no
        branch read for a command that names another repository. Each asks on a feature branch, where a merge is
        otherwise allowed, or lands on the default branch."""
        cases = [
            ("main", "git merge -m --abort feat", "default"),  # `--abort` is the message here
            ("main", "git merge --abort feat", "default"),  # not the only argument
            ("main", "git merge -X --quit feat", "default"),
            ("main", "git merge upstream/main", "default"),  # a same-named branch the branch does not track
            ("feat", "git -C . merge main", None),
            ("feat", "git --git-dir=.git merge main", None),
            ("feat", "git --work-tree . merge main", None),
            ("feat", "git -c a.b=c -C . merge main", None),
            ("feat", "GIT_DIR=.git git merge main", None),
        ]
        for here, line, branch in cases:
            self.on(here)
            with self.subTest(here=here, line=line):
                self.assertEqual(answer(line, self.repo), ("ask", [("git.merge", branch)]))

    def test_a_local_upstream_never_lowers_a_merge_into_the_default_branch(self):
        """D-S7: `git branch --set-upstream-to=feat main` is allowed, and then `git merge feat`, a bare `git merge`, and a
        `git pull` would merge a local branch into main as the branch's "own upstream". A remote's branch is the
        upstream aidd means, so a local one lowers nothing on the default branch (and nothing changes on another)."""
        with tempfile.TemporaryDirectory() as d:
            helpers.git(d, "init", "-q", "-b", "main")
            helpers.git(d, "commit", "-q", "--allow-empty", "-m", "base")
            helpers.git(d, "branch", "feat")
            self.assertEqual(answer("git branch --set-upstream-to=feat main", d)[0], "allow")
            helpers.git(d, "branch", "-q", "--set-upstream-to=feat", "main")
            helpers.git(d, "branch", "-q", "--set-upstream-to=main", "feat")
            for line in ("git merge feat", "git merge", "git merge --no-ff", "git pull", "git pull --ff-only"):
                with self.subTest(on="main", line=line):
                    self.assertEqual(answer(line, d), ("ask", [("git.merge", "default")]))
            helpers.git(d, "switch", "-q", "feat")
            for line in ("git merge main", "git merge", "git pull"):
                with self.subTest(on="feat", line=line):
                    self.assertEqual(answer(line, d), ("allow", []))
            helpers.git(d, "switch", "-q", "main")
            helpers.git(d, "update-ref", "refs/remotes/origin/main", "HEAD")
            helpers.git(d, "remote", "add", "origin", "https://example.invalid/origin.git")
            helpers.git(d, "branch", "-q", "--set-upstream-to=origin/main", "main")
            for line in ("git merge origin/main", "git merge", "git pull"):
                with self.subTest(on="main with a remote upstream", line=line):
                    self.assertEqual(answer(line, d), ("allow", []))

    def test_only_a_remote_copy_of_the_same_branch_is_the_default_branchs_own_upstream(self):
        """The security review of D-S7: on the default branch, the upstream lands nothing only when `branch.main.merge` is
        `refs/heads/main` and its remote is a configured one, not `.`. A remote copy of another branch is that branch's work."""
        with tempfile.TemporaryDirectory() as d:
            helpers.git(d, "init", "-q", "-b", "main")
            helpers.git(d, "commit", "-q", "--allow-empty", "-m", "base")
            helpers.git(d, "branch", "feat")
            helpers.git(d, "remote", "add", "origin", "https://example.invalid/origin.git")
            for name in ("main", "feat"):
                helpers.git(d, "update-ref", f"refs/remotes/origin/{name}", "HEAD")
            helpers.git(d, "branch", "-q", "--set-upstream-to=origin/main", "main")
            for line in ("git merge origin/main", "git merge", "git pull"):
                with self.subTest(upstream="origin/main", line=line):
                    self.assertEqual(answer(line, d), ("allow", []), "the control: its own branch on its remote lands nothing")
            helpers.git(d, "branch", "-q", "--set-upstream-to=origin/feat", "main")
            for line in ("git merge origin/feat", "git merge", "git pull", "git pull --ff-only"):
                with self.subTest(upstream="origin/feat", line=line):
                    self.assertEqual(answer(line, d), ("ask", [("git.merge", "default")]))
            helpers.git(d, "branch", "-q", "--set-upstream-to=origin/main", "main")
            helpers.git(d, "config", "branch.main.remote", ".")  # the same name, but the remote is this repository
            helpers.git(d, "config", "branch.main.merge", "refs/heads/feat")
            for line in ("git merge feat", "git merge", "git pull"):
                with self.subTest(upstream="local feat", line=line):
                    self.assertEqual(answer(line, d), ("ask", [("git.merge", "default")]))

    def test_the_default_branchs_upstream_is_exactly_its_own_name_on_its_remote(self):
        """The security review of D-S7: a fetch refspec can map `main` onto `refs/remotes/origin/feat`, and that is not main's own."""
        with tempfile.TemporaryDirectory() as d:
            helpers.git(d, "init", "-q", "-b", "main")
            helpers.git(d, "commit", "-q", "--allow-empty", "-m", "base")
            helpers.git(d, "remote", "add", "origin", "https://example.invalid/origin.git")
            helpers.git(d, "update-ref", "refs/remotes/origin/feat", "HEAD")
            helpers.git(d, "config", "remote.origin.fetch", "+refs/heads/main:refs/remotes/origin/feat")
            helpers.git(d, "config", "branch.main.remote", "origin")
            helpers.git(d, "config", "branch.main.merge", "refs/heads/main")
            self.assertEqual(helpers.git(d, "rev-parse", "--symbolic-full-name", "main@{u}"), "refs/remotes/origin/feat")
            for line in ("git merge origin/feat", "git merge", "git pull"):
                with self.subTest(line=line):
                    self.assertEqual(answer(line, d), ("ask", [("git.merge", "default")]))

    def test_a_name_is_read_before_the_line_runs_so_an_earlier_command_that_moves_a_ref_makes_it_unknown(self):
        """The security review of D-S7: `git update-ref refs/remotes/origin/main <sha> && git merge origin/main` merges what
        the first command made of the name. A fetch follows tags, so it moves a name too, unless it passes `--no-tags`."""
        self.on("main")
        feat = helpers.git(self.repo, "rev-parse", "feat")
        with self.reading():
            for line in (
                "git merge origin/main",
                "git fetch --no-tags && git merge origin/main",
                "git status && git merge",
                "git pull",
                "git fetch && git status",
            ):
                with self.subTest(line=line, kind="control"):
                    self.assertEqual(answer(line, self.repo), ("allow", []))
            moves = [
                f"git update-ref refs/remotes/origin/main {feat}",
                "git tag main feat",
                "git tag -f main feat",
                "git branch -u feat main",
                "git branch --set-upstream-to=feat main",
                "git branch -f main feat",
                "git branch -m main old",
                "git branch other feat",
                "git config branch.main.merge refs/heads/feat",
                "git config remote.origin.fetch +refs/heads/feat:refs/remotes/origin/main",
                "git remote set-url origin https://example.invalid/x.git",
                "git remote update",
                "git fetch origin feat:refs/remotes/origin/main",
                "git fetch",
                "git fetch origin",
                "git fetch --tags",
                "git pull",
                "git fetch --set-upstream origin feat",
                "git branch -f --track main origin/feat",
                "git checkout -B main origin/feat",
            ]
            # A named merge asks after any move. A bare merge or `@{u}` reads the local tracking ref, which only a ref write or a
            # changed upstream can move. A bare pull fetches its upstream fresh, so only a changed upstream redirects it.
            upstream = {
                "git branch -u feat main",
                "git branch --set-upstream-to=feat main",
                "git branch -m main old",
                "git config branch.main.merge refs/heads/feat",
                "git config remote.origin.fetch +refs/heads/feat:refs/remotes/origin/main",
                "git remote set-url origin https://example.invalid/x.git",
                "git remote update",
                "git branch -f main feat",
                "git fetch --set-upstream origin feat",
                "git branch -f --track main origin/feat",
                "git checkout -B main origin/feat",
            }
            tracking = upstream | {f"git update-ref refs/remotes/origin/main {feat}", "git fetch origin feat:refs/remotes/origin/main"}
            for move in moves:
                for merge in ("git merge origin/main", "git merge main", "git merge", "git merge @{u}", "git pull"):
                    asks = (
                        merge in ("git merge origin/main", "git merge main")
                        or (merge == "git pull" and move in upstream)
                        or (merge in ("git merge", "git merge @{u}") and move in tracking)
                    )
                    with self.subTest(move=move, merge=merge):
                        level, actions = answer(f"{move} && {merge}", self.repo)  # the first command may match an action of its own
                        if asks:
                            self.assertEqual(level, "ask")
                            self.assertIn(("git.merge", "default"), actions)
                        else:
                            self.assertNotIn(("git.merge", "default"), actions, "a move that cannot redirect this merge leaves it alone")
            for move in ("git branch -f main feat", "git fetch origin feat:refs/remotes/origin/main", "git branch -u feat main"):
                for shell in ("bash -c", "bash -lc", "sh -c"):
                    with self.subTest(move=move, shell=shell, case="inside one wrapped command"):
                        level, actions = answer(f"{shell} '{move} && git merge origin/main'", self.repo)
                        self.assertEqual(level, "ask")
                        self.assertIn(("git.merge", "default"), actions)
            for line in ("git -c branch.main.merge=refs/heads/feat merge", "git -c remote.origin.fetch=+refs/heads/feat:refs/remotes/origin/main pull"):
                with self.subTest(line=line, case="a -c on the merge's own call"):
                    self.assertEqual(answer(line, self.repo), ("ask", [("git.merge", "default")]))
            for line in (
                "GIT_TRACE=0 git branch -f main feat && git merge origin/main",
                "git merge origin/main && git branch -f main feat && git merge origin/main",
            ):
                with self.subTest(line=line, case="a setting before git, and the same merge again after a move"):
                    level, actions = answer(line, self.repo)
                    self.assertEqual(level, "ask")
                    self.assertIn(("git.merge", "default"), actions)
            with self.subTest(case="a read-only branch listing and git config get"):
                self.assertEqual(answer("git branch --show-current && git config --get branch.main.merge && git merge origin/main", self.repo), ("allow", []))

    def test_a_name_that_git_reads_as_another_ref_is_not_the_branch_checked_out(self):
        """The security review of D-S7: `main` can be a tag (git prefers it to the branch) or also `refs/remotes/main`, so
        the text of a name proves nothing. Each name is resolved the way git does, and only the full name counts."""
        with tempfile.TemporaryDirectory() as d:
            helpers.git(d, "init", "-q", "-b", "main")
            helpers.git(d, "commit", "-q", "--allow-empty", "-m", "base")
            helpers.git(d, "switch", "-q", "-c", "feat")
            helpers.git(d, "commit", "-q", "--allow-empty", "-m", "feat work")
            helpers.git(d, "switch", "-q", "main")
            self.assertEqual(answer("git merge main", d), ("allow", []), "the control: the plain name is the branch")
            self.assertEqual(answer("git merge heads/main", d), ("allow", []), "and so is a longer name for it")
            self.assertEqual(answer("git merge refs/heads/main", d), ("allow", []))
            helpers.git(d, "update-ref", "refs/remotes/main", "feat")
            self.assertEqual(answer("git merge main", d), ("ask", [("git.merge", "default")]), "two refs share the name")
            helpers.git(d, "update-ref", "-d", "refs/remotes/main")
            helpers.git(d, "tag", "main", "feat")
            for line in ("git merge main", "git merge --ff-only main"):
                with self.subTest(line=line):
                    self.assertEqual(answer(line, d), ("ask", [("git.merge", "default")]), "git merges the tag")
            self.assertEqual(answer("git merge nothing-by-this-name", d), ("ask", [("git.merge", "default")]))

    def test_a_local_branch_named_like_the_remote_one_never_moves_the_default_branch(self):
        """`symbolic-ref --short refs/remotes/origin/HEAD` prints `remotes/origin/main` once a branch is named
        `origin/main`, and `origin/main` then names that branch: the default branch is read by full names."""
        self.on("main")
        helpers.git(self.repo, "branch", "origin/main", "feat")
        try:
            self.assertEqual(answer("git merge feat", self.repo), ("ask", [("git.merge", "default")]))
        finally:
            helpers.git(self.repo, "branch", "-D", "origin/main")

    def test_an_unknown_default_branch_asks(self):
        with tempfile.TemporaryDirectory() as d:
            helpers.git(d, "init", "-q", "-b", "trunk")  # no remote, and no main or master: git cannot tell
            helpers.git(d, "commit", "-q", "--allow-empty", "-m", "base")
            helpers.git(d, "branch", "feat")
            self.assertEqual(answer("git merge feat", d), ("ask", [("git.merge", None)]))

    def test_a_detached_head_asks_since_git_cannot_tell(self):
        helpers.git(self.repo, "switch", "-q", "--detach", "main")
        self.assertEqual(answer("git merge feat", self.repo), ("ask", [("git.merge", None)]))

    def test_the_branch_a_person_names_wins(self):
        self.on("feat")
        self.assertEqual(risk.command_level(risk.rule_set(None), "git merge main", branch="default", cwd=self.repo)["level"], "ask")
        # A PR/MR merges into its base, so the branch the agent is on never lowers it.
        self.assertEqual(risk.command_level(risk.rule_set(None), "gh pr merge 12", branch="own", cwd=self.repo)["level"], "ask")

    def test_the_merge_asks_only_while_the_rule_does(self):
        self.on("main")
        rs = risk.rule_set(None)
        lowered = dataclasses.replace(rs, rules=[r for r in rs.rules if r.action != "git.merge"] + [Rule(action="git.merge", level="report")])
        self.assertEqual(answer("git merge feat", self.repo, lowered)[0], "report")

    def test_gh_pr_merge_still_asks_on_any_branch(self):
        self.on("feat")
        self.assertEqual(answer("gh pr merge 12", self.repo), ("ask", [("pr.merge", None)]))

    def test_a_pull_with_any_word_but_an_option_lands_work(self):
        """On the default branch, a `git pull` with any word
        that is no option asks, with no reading of what it names, and one with only options pulls the branch's own
        upstream, so it asks nothing. On another branch a pull never asks."""
        lines = {
            "git pull": "allow",
            "git pull --ff-only": "allow",
            "git pull --rebase": "allow",
            "git pull --no-rebase": "allow",
            "git pull origin main": "ask",
            "git pull https://x/y.git": "ask",
            "git pull ../other": "ask",
            "git pull . feat": "ask",
            "git pull origin refs/heads/main:x": "ask",
            "git pull --rebase origin feat": "ask",
        }
        for here in ("main", "feat"):
            self.on(here)
            for line, want in lines.items():
                with self.subTest(here=here, line=line):
                    self.assertEqual(answer(line, self.repo)[0], want if here == "main" else "allow")
        self.on("feat")
        for line in ("git -C ../trunk pull", "git --git-dir=../trunk/.git pull --ff-only", "git -C . merge --abort"):
            with self.subTest(line=line):
                self.assertEqual(answer(line, self.repo), ("ask", [("git.merge", None)]))  # another repository counts first

    def test_git_merge_reads_its_branch_and_pr_merge_never_does(self):
        """A local merge is `git.merge`, allowed only on one's own branch, while `pr.merge` asks
        whatever branch a person names."""
        rs = risk.rule_set(None)
        for branch, want in (("own", "allow"), ("default", "ask"), ("shared", "ask"), (None, "ask")):
            with self.subTest(branch=branch):
                self.assertEqual(risk.level_of(rs, "git.merge", branch=branch)[0], want)
                self.assertEqual(risk.level_of(rs, "pr.merge", branch=branch)[0], "ask")
        self.on("main")
        self.assertEqual(risk.command_level(rs, "gh pr merge 12", branch="own", cwd=self.repo)["level"], "ask")
        self.assertEqual(risk.command_level(rs, "git merge feat", branch="own", cwd=self.repo)["level"], "allow")


class ACdEarlierOnTheLineMovesTheBranchRead(unittest.TestCase):
    """A `cd` or `pushd` before the merge or push changes the folder whose branch is read,
    and a target aidd cannot resolve asks. A bare `-` names the branch checked out before."""

    def test_each_form(self):
        with tempfile.TemporaryDirectory() as d:
            trunk, feat = Path(d, "trunk"), Path(d, "feat")
            trunk.mkdir()
            helpers.git(str(trunk), "init", "-q", "-b", "main")
            helpers.git(str(trunk), "commit", "-q", "--allow-empty", "-m", "base")
            helpers.git(str(trunk), "worktree", "add", "-q", "-b", "feat", str(feat))
            cases = [
                (feat, "git merge main", "allow"),  # merging main into one's own branch
                (feat, "cd ../trunk && git merge feat", "ask"),
                (feat, "pushd ../trunk; git merge feat", "ask"),
                (feat, "cd ../trunk && git push", "ask"),
                (feat, "cd $REPO && git merge main", "ask"),
                (feat, "cd - && git merge main", "ask"),
                (feat, "cd ~bob/repo && git merge main", "ask"),
                (feat, "cd ../missing && git merge main", "ask"),
                (feat, "cd . && git merge main", "allow"),
                (trunk, "git merge -", "ask"),
            ]
            for folder, line, want in cases:
                with self.subTest(folder=folder.name, line=line):
                    self.assertEqual(risk.command_level(risk.rule_set(None), line, cwd=str(folder))["level"], want)

    def test_a_form_aidd_cannot_model_asks(self):
        """The same merge in another folder is read again, a `cd` behind a group or a
        `builtin` prefix still moves the folder, and a `cd` inside a wrapped command, or under `CDPATH`, makes the
        folder unknown, so a merge or a push after it asks."""
        with tempfile.TemporaryDirectory() as d:
            trunk, feat = Path(d, "trunk"), Path(d, "feat")
            trunk.mkdir()
            helpers.git(str(trunk), "init", "-q", "-b", "main")
            helpers.git(str(trunk), "commit", "-q", "--allow-empty", "-m", "base")
            helpers.git(str(trunk), "worktree", "add", "-q", "-b", "feat", str(feat))
            cases = [
                ("git merge feat && cd ../trunk && git merge feat", {}, "ask"),
                ("(cd ../trunk && git merge feat)", {}, "ask"),
                ("{ cd ../trunk; git merge feat; }", {}, "ask"),
                ("builtin cd ../trunk && git merge feat", {}, "ask"),
                ("command cd ../trunk && git merge feat", {}, "ask"),
                ("bash -c 'cd ../trunk && git merge feat'", {}, "ask"),
                ("sh -c 'cd ../trunk' && git merge main", {}, "ask"),
                ("eval 'cd ../trunk'; git merge main", {}, "ask"),
                ("(cd ../trunk && git status); git merge main", {}, "ask"),  # the subshell's folder ends with it
                ("bash -c 'cd ../trunk && git push'", {}, "ask"),
                ("(cd ../trunk); git merge main", {}, "allow"),  # a whole subshell leaves the folder as it was
                ("cd ../feat && git merge main", {"CDPATH": d}, "ask"),
                ("cd ../feat && git merge main", {}, "allow"),
                ("bash -c 'git status' && git merge main", {}, "allow"),
            ]
            for line, env, want in cases:
                with self.subTest(line=line, env=env), mock.patch.dict(os.environ, env):
                    os.environ.pop("CDPATH", None) if not env else None
                    self.assertEqual(risk.command_level(risk.rule_set(None), line, cwd=str(feat))["level"], want)


class TheFolderTheCommandRunsInIsRead(unittest.TestCase):
    """The security confirm of ace25f6: the MCP `risk` tool runs in its own folder, so `folder`, and `--folder` on the
    CLI, name the folder the command runs in. A path that is no git checkout counts as another repository, so it asks."""

    def test_each_form(self):
        from aidd.cli import mcp_server

        with tempfile.TemporaryDirectory() as d:
            trunk, feat, plain = Path(d, "trunk"), Path(d, "feat"), Path(d, "plain")
            trunk.mkdir()
            plain.mkdir()
            helpers.git(str(trunk), "init", "-q", "-b", "main")
            helpers.git(str(trunk), "commit", "-q", "--allow-empty", "-m", "base")
            helpers.git(str(trunk), "worktree", "add", "-q", "-b", "feat", str(feat))
            cases = [
                (feat, "git merge feat", None, "allow"),  # the session's own folder: merging feat into itself
                (feat, "git merge feat", "../trunk", "ask"),  # main is checked out there
                (feat, "git merge feat", str(trunk), "ask"),
                (trunk, "git merge main", "../feat", "allow"),
                (feat, "git merge main", "../missing", "ask"),
                (feat, "git merge main", str(plain), "ask"),  # no git checkout
            ]
            for session, line, folder, want in cases:
                with self.subTest(session=session.name, line=line, folder=folder):
                    args = ["risk", "--command", line, "--json"] + (["--folder", folder] if folder else [])
                    done = helpers.aidd_subprocess(*args, cwd=session)
                    self.assertEqual(json.loads(done.stdout)["level"], want, done.stderr)
                    is_error, text = mcp_server.call("risk", {"command": line, **({"folder": folder} if folder else {})}, str(session))
                    self.assertFalse(is_error, text)
                    self.assertEqual(json.loads(text)["level"], want)


class TheHarnessRulesHoldNoLocalMerge(unittest.TestCase):
    """No harness rule can see the branch, so a `git merge` pattern would ask on every merge of main into a feature branch."""

    def patterns(self, rs) -> list[str]:
        return risk.harness_patterns(rs, "main")

    def test_no_format_gets_a_git_merge_rule_while_one_s_own_branch_allows(self):
        patterns = self.patterns(risk.rule_set(None))
        self.assertIn("gh pr merge*", patterns)
        self.assertFalse([p for p in patterns if p.startswith(("git merge", "git pull"))])
        for fmt in harness_rules.FORMATS:
            with self.subTest(fmt=fmt), tempfile.TemporaryDirectory() as d:
                risk.apply_harness_rules(Path(d), fmt, patterns)
                text = "".join(p.read_text() for p in Path(d).rglob("*") if p.is_file())
                for words in ("git merge", "git pull"):
                    self.assertNotIn(words, text.replace("\\", ""))
                    self.assertNotIn(json.dumps(words.split())[:-1], text)

    def test_a_merge_that_asks_on_every_branch_reaches_the_harness(self):
        rs = risk.rule_set(None)
        strict = dataclasses.replace(rs, rules=[r for r in rs.rules if r.action != "git.merge"] + [Rule(action="git.merge", level="ask")])
        self.assertIn("git merge *", self.patterns(strict))
        self.assertIn("git pull *", self.patterns(strict))


if __name__ == "__main__":
    unittest.main()
