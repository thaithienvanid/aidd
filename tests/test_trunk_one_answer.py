"""One answer to "which branch is the trunk". `default_base` (what `aidd test --changed` and the branch base compare against) and
`default_branches` (what the push rules guard) read one function, so for every repository shape they name the same branch, or
both say they cannot tell. A repository whose trunk is neither `main` nor `master` once broke `--changed` while its pushes read
that trunk as the default branch."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers

from aidd.kernel import git as gitutil


def repo(root: str, *, branch: str = "main", config: str | None = None, remote_heads: tuple[str, ...] = (), origin_head: str | None = None) -> None:
    """A repository on `branch` with one commit; `config` is its own `init.defaultBranch`, `remote_heads` the branches origin has
    (as remote-tracking refs), and `origin_head` the one origin names its default."""
    helpers.git(root, "init", "-q", "-b", branch)
    helpers.git(root, "commit", "-q", "--allow-empty", "-m", "first")
    if config:
        helpers.git(root, "config", "--local", "init.defaultBranch", config)
    if remote_heads:
        helpers.git(root, "remote", "add", "origin", "https://example.invalid/origin.git")
    for name in remote_heads:
        helpers.git(root, "update-ref", f"refs/remotes/origin/{name}", "HEAD")
    if origin_head:
        helpers.git(root, "symbolic-ref", "refs/remotes/origin/HEAD", f"refs/remotes/origin/{origin_head}")


# (name, shape, the trunk it tells as (base, branch), or None when it cannot tell)
SHAPES = [
    ("main only", {}, ("main", "main")),
    ("master only", {"branch": "master"}, ("master", "master")),
    ("trunk, nothing says so", {"branch": "trunk"}, None),
    ("trunk, named by the repository's config", {"branch": "trunk", "config": "trunk"}, ("trunk", "trunk")),
    ("config names a branch that does not exist", {"branch": "trunk", "config": "develop"}, None),
    ("develop only on origin, named by config", {"branch": "feat", "config": "develop", "remote_heads": ("develop",)}, ("origin/develop", "develop")),
    ("origin names its default", {"branch": "feat", "remote_heads": ("develop",), "origin_head": "develop"}, ("origin/develop", "develop")),
    ("origin's default has a slash", {"branch": "feat", "remote_heads": ("release/1.0",), "origin_head": "release/1.0"}, ("origin/release/1.0", "release/1.0")),
    ("config names a slash branch", {"branch": "release/2", "config": "release/2"}, ("release/2", "release/2")),
    ("main beats the config", {"branch": "main", "config": "other"}, ("main", "main")),
    ("origin/main beats the config", {"branch": "feat", "config": "develop", "remote_heads": ("main", "develop")}, ("origin/main", "main")),
]


class OneTrunk(unittest.TestCase):
    def tells(self, root: str) -> tuple[tuple[str, str] | None, tuple[list[str], bool]]:
        try:
            base: tuple[str, str] | None = (gitutil.default_base(root), "")
        except gitutil.GitError:
            base = None
        return base, gitutil.default_branches(root)

    def test_both_functions_name_the_same_trunk_for_every_shape(self):
        for name, shape, trunk in SHAPES:
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                repo(d, **shape)
                base, (branches, sure) = self.tells(d)
                if trunk is None:
                    self.assertIsNone(base, "default_base cannot tell, so default_branches says it cannot either")
                    self.assertFalse(sure)
                    continue
                self.assertIsNotNone(base, "default_base tells the trunk too")
                self.assertEqual((base[0], branches, sure), (trunk[0], [trunk[1]], True))

    def test_a_push_that_asks_for_want_of_a_trunk_says_so_and_how_to_name_one(self):
        for name, shape, trunk in SHAPES:
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                repo(d, **shape)
                run = helpers.aidd_here("risk", "--command", f"git push origin {shape.get('branch', 'main')}", "--json", cwd=d)
                notes = json.loads(run.stdout)["notes"]
                said = [n for n in notes if "cannot tell the default branch" in n]
                self.assertEqual(len(said), 1 if trunk is None else 0, notes)
                if said:
                    self.assertIn("git config init.defaultBranch <branch>", said[0])

    def test_a_global_default_branch_name_is_never_this_repositorys_trunk(self):
        with tempfile.TemporaryDirectory() as d:
            repo(d, branch="trunk")
            home = Path(d) / "home.gitconfig"
            home.write_text("[init]\n\tdefaultBranch = trunk\n", encoding="utf-8")
            with mock.patch.dict("os.environ", {"GIT_CONFIG_GLOBAL": str(home)}):
                base, (_, sure) = self.tells(d)
        self.assertIsNone(base)
        self.assertFalse(sure)

    def test_when_it_cannot_tell_the_error_names_both_ways_to_say_it(self):
        with tempfile.TemporaryDirectory() as d:
            repo(d, branch="trunk")
            with self.assertRaises(gitutil.GitError) as raised:
                gitutil.default_base(d)
        self.assertIn("git config init.defaultBranch <branch>", str(raised.exception))
        self.assertIn("git remote set-head origin --auto", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
