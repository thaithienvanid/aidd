"""A name that git reads as another ref cannot turn the default branch into something else: a tag called `origin/main`,
and a plain `git fetch` that brings one. T-GIT-02 in docs/security/threat-models/kernel-git.md."""

import json
import tempfile
import unittest
from pathlib import Path

import helpers
from aidd import risk
from aidd.kernel import git as gitutil
from aidd.kernel import git_calls
from aidd.setup import adoption


def clone_with_tag_origin_main(d: str) -> str:
    """A repository whose origin has a `main`, and a local tag `origin/main` on another commit."""
    helpers.git(d, "init", "-q", "-b", "main")
    helpers.git(d, "commit", "-q", "--allow-empty", "-m", "base")
    helpers.git(d, "remote", "add", "origin", "https://example.invalid/origin.git")
    helpers.git(d, "update-ref", "refs/remotes/origin/main", "HEAD")
    helpers.git(d, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    helpers.git(d, "commit", "-q", "--allow-empty", "-m", "other work")
    helpers.git(d, "tag", "origin/main", "HEAD")
    return d


class ATagCalledLikeTheRemoteDefaultBranch(unittest.TestCase):
    def test_default_branches_reads_full_ref_names_so_a_tag_origin_main_changes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            clone_with_tag_origin_main(d)
            self.assertEqual(gitutil.default_branches(d), (["main"], True))

    def test_the_ask_rules_still_cover_a_push_to_main_when_a_tag_is_called_origin_main(self):
        with tempfile.TemporaryDirectory() as d:
            clone_with_tag_origin_main(d)
            root = Path(d)
            (root / ".claude").mkdir()
            adoption.write_ask_rules(root, ["claude-code"], [])
            ask = json.loads((root / ".claude" / "settings.json").read_text())["permissions"]["ask"]
            for pattern in ("Bash(git push * main)", "Bash(git push * *:main)", "Bash(git push * refs/heads/main)"):
                with self.subTest(pattern=pattern):
                    self.assertIn(pattern, ask)
            self.assertNotIn("Bash(git push * origin/main)", ask)


def answer(line: str, cwd: str) -> tuple[str, list[tuple[str, str | None]]]:
    a = risk.command_level(risk.rule_set(None), line, cwd=cwd)
    return a["level"], [(x["action"], x["branch"]) for x in a["actions"]]


class AFetchedTagCanTakeTheNameOfARemoteBranch(unittest.TestCase):
    """T-GIT-02: a plain `git fetch` follows the tags of what it brings, so `origin/main` can name a tag the line made."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        origin, seed, self.clone = (str(Path(tmp.name) / n) for n in ("origin.git", "seed", "clone"))
        helpers.git(tmp.name, "init", "-q", "--bare", "-b", "main", origin)
        helpers.git(tmp.name, "clone", "-q", origin, seed)
        helpers.git(seed, "commit", "-q", "--allow-empty", "-m", "base")
        helpers.git(seed, "push", "-q", "origin", "main")
        helpers.git(tmp.name, "clone", "-q", origin, self.clone)
        # Work that reaches origin after the clone, with a tag called like the branch: the clone has not seen it yet.
        helpers.git(seed, "switch", "-q", "-c", "evil")
        helpers.git(seed, "commit", "-q", "--allow-empty", "-m", "evil work")
        helpers.git(seed, "tag", "origin/main")
        helpers.git(seed, "push", "-q", "origin", "evil", "refs/tags/origin/main")

    def test_a_fetch_before_a_merge_makes_the_name_unknown_unless_it_takes_no_tags(self):
        helpers.git(self.clone, "fetch", "-q")
        names = {n: helpers.git(self.clone, "rev-parse", n) for n in ("origin/main", "refs/tags/origin/main", "refs/remotes/origin/main")}
        self.assertEqual(names["origin/main"], names["refs/tags/origin/main"], "the control: the fetch made a tag, and git reads the name as the tag")
        self.assertNotEqual(names["origin/main"], names["refs/remotes/origin/main"])
        helpers.git(self.clone, "tag", "-d", "origin/main")
        asks = (
            "git fetch && git merge origin/main",
            "git fetch origin && git merge origin/main",
            "git pull && git merge origin/main",
            "git fetch --tags && git merge origin/main",
        )
        for line in asks:
            with self.subTest(line=line):
                self.assertEqual(answer(line, self.clone), ("ask", [("git.merge", "default")]))
        allows = ("git fetch --no-tags && git merge origin/main", "git merge origin/main", "git pull", "git fetch")
        for line in allows:
            with self.subTest(line=line):
                self.assertEqual(answer(line, self.clone), ("allow", []))


class TheSubcommandIsFoundPastGitsOwnOptions(unittest.TestCase):
    """`git --git-dir <path> status` has the subcommand `status`: an option that takes its value as the next word must not
    leave that word as the subcommand, or a hook-starting call reads as `<path>` and skips the hook guard."""

    def test_an_option_with_a_value_in_two_words_is_stepped_over(self):
        rows = {
            ("--git-dir", "/x/.git", "status"): (2, "status"),
            ("--work-tree", "/x", "diff", "HEAD"): (2, "diff"),
            ("--namespace", "ns", "fetch"): (2, "fetch"),
            ("--config-env", "alias.x=V", "status"): (2, "status"),
            ("--git-dir=/x/.git", "status"): (1, "status"),
            ("-c", "a=b", "-C", "/x", "--git-dir", "/y", "--work-tree", "/z", "log"): (8, "log"),
            ("--no-pager", "status"): (1, "status"),
            ("--git-dir",): (1, ""),
        }
        for args, expected in rows.items():
            with self.subTest(args=args):
                self.assertEqual(git_calls.subcommand(list(args)), expected)
        for args in (("--git-dir", "/x/.git", "status"), ("--work-tree", "/x", "diff")):
            with self.subTest(guard=args):
                self.assertTrue(git_calls.starts_hooks(list(args)))
