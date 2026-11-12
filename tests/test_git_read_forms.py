"""The git calls aidd keeps inside `shared_reads` are never stale, and the table that says which call is a read holds.

Invariant: inside one `shared_reads` scope, a kept read is never returned after a write that could change its answer. A
write is any call that git itself shows changing the refs, HEAD, or the config, and any call the table does not know.
The table is `git_calls`: a form is a read only where a row names it, so a new or unknown form is a write (fail closed).

Each form below is run against a real repository, so what holds does not depend on this file's reading of git's manual.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import NamedTuple

import helpers
import shared_reads

from aidd.kernel import git as kernel_git
from aidd.kernel import git_reads
from aidd.kernel import git_calls, git_forms


class Form(NamedTuple):
    argv: tuple[str, ...]
    aidd: str  # what aidd does with the call: "kept" (answered once per scope), "read" (run each time, drops nothing), "write" (drops what was kept)
    reason: str


def form(aidd: str, reason: str, *argv: str) -> Form:
    return Form(argv, aidd, reason)


# One row per form of git call the product issues, and the adjacent forms that differ only in an option that writes.
FORMS = (
    form("kept", "reads a ref and its object", "rev-parse", "HEAD"),
    form("kept", "reads a ref and its object", "rev-parse", "-q", "--verify", "refs/heads/dev^{commit}"),
    form("kept", "reads a ref name in full", "rev-parse", "--symbolic-full-name", "HEAD"),
    form("kept", "reads where the repository is", "rev-parse", "--show-toplevel"),
    form("kept", "reads the branch HEAD names", "symbolic-ref", "-q", "--short", "HEAD"),
    form("kept", "reads the branch HEAD names", "symbolic-ref", "-q", "HEAD"),
    form("kept", "reads refs", "for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes/origin"),
    form("kept", "reads commits", "merge-base", "main", "feat"),
    form("kept", "reads commits", "merge-base", "--is-ancestor", "main", "feat"),
    form("kept", "reads one tree", "ls-tree", "-r", "-z", "--full-tree", "HEAD"),
    form("kept", "reads the config", "config", "--get", "user.email"),
    form("kept", "reads the config", "config", "--local", "--get", "init.defaultBranch"),
    form("kept", "reads the config", "remote"),
    form("kept", "reads where a symbolic ref points: one name, no -d or -m (git-symbolic-ref)", "symbolic-ref", "-q", "refs/remotes/origin/HEAD"),
    form("kept", "reads where a symbolic ref points, with the options in the other order", "symbolic-ref", "--short", "-q", "HEAD"),
    form("kept", "reads the config for one name (--get-regexp prints each match)", "config", "-z", "--get-regexp", "^(push\\.default|remote\\..*\\.push)$"),
    form("kept", "reads the config for one name, as a boolean", "config", "--type=bool", "-z", "--get-regexp", "^remote\\..*\\.mirror$"),
    form("kept", "reads the config for one name (--get-all prints each value)", "config", "--get-all", "push.default"),
    form("kept", "reads the whole config", "config", "--list"),
    form("kept", "reads the config for one name, with no option", "config", "push.default"),
    form("kept", "reads a remote's URL", "remote", "get-url", "origin"),
    form("kept", "lists the tags of one object", "tag", "--points-at", "HEAD"),
    form("kept", "counts commits", "rev-list", "--count", "--end-of-options", "main..feat"),
    form("read", "lists the work trees", "worktree", "list", "--porcelain", "-z"),
    form("read", "tells which ignore rule matches a path, and writes nothing", "check-ignore", "-v", "--no-index", "-q", "a.txt"),
    form("read", "reads the work tree", "status", "--porcelain", "-z"),
    form("read", "reads files and the index", "ls-files", "-z"),
    form("read", "reads objects", "cat-file", "-e", "HEAD"),
    form("read", "reads objects", "show", "HEAD:a.txt"),
    form("read", "reads commits", "log", "-z", "--format=%H", "HEAD"),
    form("read", "reads a diff", "diff", "--name-only", "-z", "HEAD"),
    form("write", "moves HEAD", "switch", "-q", "main"),
    form("write", "makes a branch and moves HEAD", "switch", "-qc", "new"),
    form("write", "moves HEAD", "checkout", "-q", "main"),
    form("write", "makes a branch", "branch", "made"),
    form("write", "deletes a branch", "branch", "-D", "dev"),
    form("write", "makes a tag", "tag", "made"),
    form("write", "deletes a tag", "tag", "-d", "v1"),
    form("write", "writes a ref", "update-ref", "refs/heads/made", "HEAD"),
    form("write", "deletes a ref", "update-ref", "-d", "refs/heads/dev"),
    form("write", "sets a symbolic ref", "symbolic-ref", "HEAD", "refs/heads/main"),
    form("write", "points a symbolic ref elsewhere", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/other"),
    form("write", "deletes a symbolic ref (an abbreviation of --delete)", "symbolic-ref", "--del", "refs/remotes/origin/HEAD"),
    form("write", "deletes a symbolic ref", "symbolic-ref", "-qd", "refs/remotes/origin/HEAD"),
    form("write", "sets a value, whatever it spells (options come first)", "config", "user.email", "--get"),
    form("write", "sets a value", "config", "--local", "push.default", "upstream"),
    form("write", "removes a value", "config", "--unset", "init.defaultBranch"),
    form("write", "adds a value", "config", "--add", "push.default", "upstream"),
    form("write", "no row names a --get beside --add", "config", "--get", "--add", "push.default"),
    form("write", "no row names an abbreviation, though git reads --get-reg as --get-regexp", "config", "--get-reg", "^push"),
    form("write", "no row names an option it does not list", "config", "--local", "--bogus", "push.default"),
    form("write", "a second name sets the symbolic ref (git-symbolic-ref)", "symbolic-ref", "-q", "--short", "HEAD", "refs/heads/main"),
    form("write", "deletes a symbolic ref", "symbolic-ref", "-q", "--short", "--delete", "refs/remotes/origin/HEAD"),
    form("write", "writes the file --output names, which no row allows", "diff", "--output=out.txt", "HEAD"),
    form("write", "git 2.46 runs the editor on the config: `edit` is a subcommand, and a key holds a dot", "config", "edit"),
    form("write", "git 2.46 lists the config: `list` is a subcommand, so no row takes it for a key", "config", "list"),
    form("write", "adds a remote", "remote", "add", "other", "https://example.invalid/other.git"),
    form("write", "deletes the remote's default branch", "remote", "set-head", "origin", "-d"),
    form("write", "makes a commit and moves a branch", "commit", "-q", "--allow-empty", "-m", "more"),
    form("write", "moves a branch", "reset", "-q", "--soft", "HEAD~1"),
    form("write", "adds a worktree and a ref entry", "worktree", "add", "-q", "--detach", "../elsewhere"),
    form("write", "stores a stash ref", "stash", "push", "--include-untracked", "-q"),
    form("write", "writes objects, and a kept read may have found one missing", "hash-object", "-w", "a.txt"),
    form("write", "is a form no row names, so it fails closed", "frobnicate", "--now"),
)
# A write must show a change of the refs, HEAD, or config here, so the table is no vacuous pass. These do not: each is
# classed a write for being no row (git reads some as reads, or changes a file the state does not hold).
CHANGES_NOTHING_HERE = {
    ("worktree", "add", "-q", "--detach", "../elsewhere"),
    ("stash", "push", "--include-untracked", "-q"),
    ("config", "--get", "--add", "push.default"),
    ("config", "--get-reg", "^push"),
    ("config", "--local", "--bogus", "push.default"),
    ("diff", "--output=out.txt", "HEAD"),
    ("config", "edit"),
    ("config", "list"),
    ("hash-object", "-w", "a.txt"),
}


# The kept reads checked against each write: one of each kind of answer (a ref, HEAD's branch, a symbolic ref, a set of refs,
# commits, one setting, the whole config, a remote's URL).
CHECKED_AGAINST_WRITES = (
    ("rev-parse", "HEAD"),
    ("symbolic-ref", "-q", "--short", "HEAD"),
    ("symbolic-ref", "-q", "refs/remotes/origin/HEAD"),
    ("for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes/origin"),
    ("merge-base", "main", "feat"),
    ("config", "--local", "--get", "init.defaultBranch"),
    ("config", "--list"),
    ("remote", "get-url", "origin"),
)


def build(root: str) -> None:
    """main with two commits, a tag, branches dev and feat (checked out), a remote with its tracking ref and default branch."""
    helpers.git(root, "init", "-q", "-b", "main")
    Path(root, "a.txt").write_text("a\n", encoding="utf-8")
    helpers.git(root, "add", ".")
    helpers.git(root, "commit", "-qm", "one")
    helpers.git(root, "commit", "-q", "--allow-empty", "-m", "two")
    helpers.git(root, "tag", "v1")
    helpers.git(root, "branch", "dev")
    helpers.git(root, "remote", "add", "origin", "https://example.invalid/origin.git")
    helpers.git(root, "update-ref", "refs/remotes/origin/main", "main")
    helpers.git(root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    helpers.git(root, "config", "--local", "init.defaultBranch", "main")
    helpers.git(root, "config", "--local", "push.default", "current")
    helpers.git(root, "switch", "-qc", "feat")


def plain(root: str, argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    """git itself, outside aidd, that may fail: only the state it leaves behind is read. An editor it starts changes nothing."""
    env = {**os.environ, "GIT_EDITOR": "true"}
    return subprocess.run(["git", *argv], cwd=root, capture_output=True, text=True, encoding="utf-8", check=False, stdin=subprocess.DEVNULL, env=env)


class Repositories(unittest.TestCase):
    """Each test copies the repository the class built once."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.template = str(Path(cls.tmp.name).resolve() / "template")
        Path(cls.template).mkdir()
        build(cls.template)
        cls.count = 0

    def copy(self) -> str:
        type(self).count += 1
        folder = str(Path(self.tmp.name).resolve() / f"copy{type(self).count}")
        shutil.copytree(self.template, folder, symlinks=True)
        return folder


def aidd_class(argv: tuple[str, ...]) -> str:
    args = list(argv)
    return "write" if git_calls.may_write(args) else "kept" if git_calls.kept_shape(args) else "read"


class EachFormIsClassedAsGitShowsIt(Repositories):
    def test_a_call_that_changes_the_refs_or_config_is_classed_a_write(self):
        """The soundness half: git run alone on each form either leaves the refs, HEAD, and config as they were, or aidd calls it a write."""
        for row in FORMS:
            with self.subTest(argv=row.argv):
                root = self.copy()
                before = shared_reads.ref_state(root)
                plain(root, row.argv)
                changed = shared_reads.ref_state(root) != before
                if row.aidd != "write":
                    self.assertFalse(changed, f"{row.reason}: git changed the state, so aidd must class it a write")
                elif row.argv not in CHANGES_NOTHING_HERE and row.argv[0] != "frobnicate":
                    self.assertTrue(changed, f"{row.reason}: the control: this write must show a change here")

    def test_aidd_classes_each_form_as_the_table_says(self):
        for row in FORMS:
            with self.subTest(argv=row.argv):
                self.assertEqual(aidd_class(row.argv), row.aidd, row.reason)

    def test_the_answer_of_a_kept_read_ignores_the_work_tree(self):
        """A kept read depends on refs, config, and objects only, so a file written in the work tree (aidd's own writer) cannot stale it."""
        kept = [row for row in FORMS if row.aidd == "kept"]
        for row in kept:
            with self.subTest(argv=row.argv):
                root = self.copy()
                first = plain(root, row.argv)
                Path(root, "a.txt").write_text("changed\n", encoding="utf-8")
                Path(root, "new.txt").write_text("new\n", encoding="utf-8")
                Path(root, ".gitignore").write_text("*.log\n", encoding="utf-8")
                again = plain(root, row.argv)
                self.assertEqual((again.returncode, again.stdout), (first.returncode, first.stdout))


def answers(root: str, reads: list[Form]) -> list[str]:
    return [kernel_git.run(list(r.argv), root, check=False) for r in reads]


class AKeptReadIsNeverReturnedAfterAWrite(Repositories):
    def test_every_kept_read_after_every_write_is_what_git_answers_fresh(self):
        """The invariant. Kept reads are filled, one write runs through aidd, and each read must equal a fresh read of the same state."""
        reads = [row for row in FORMS if row.argv in CHECKED_AGAINST_WRITES]
        self.assertEqual({row.aidd for row in reads}, {"kept"})
        for write in (row for row in FORMS if row.aidd == "write" and row.argv not in CHANGES_NOTHING_HERE and row.argv[0] != "frobnicate"):
            with self.subTest(write=write.argv):
                root = self.copy()
                with git_reads.shared_reads():
                    answers(root, reads)  # fills the scope
                    kernel_git.run(list(write.argv), root, check=False)
                    inside = answers(root, reads)
                self.assertEqual(inside, answers(root, reads), "a read kept before the write was returned after it")

    def test_a_write_that_fails_still_drops_what_was_kept(self):
        root = self.copy()
        with git_reads.shared_reads():
            self.assertEqual(kernel_git.current_branch(root), "feat")
            plain(root, ("switch", "-q", "main"))  # a child aidd does not run: the scope cannot see it, so this read is the kept one
            self.assertEqual(kernel_git.current_branch(root), "feat", "the control: the kept read does not see a write aidd did not run")
            kernel_git.run(["switch", "-q", "no-such-branch"], root, check=False)
            self.assertEqual(kernel_git.current_branch(root), "main", "the failed write dropped what was kept")


class TheTableFailsClosed(Repositories):
    def test_each_row_names_its_own_example_and_the_example_changes_nothing(self):
        for row in git_forms.FORMS:
            with self.subTest(name=row.name, example=row.example):
                self.assertTrue(row.reason and row.example[0] == row.name)
                self.assertIs(git_forms.read_form(row.name, list(row.example[1:])), row)
                self.assertEqual(aidd_class(row.example), "kept" if row.keeps else "read")
                root = self.copy()
                before = shared_reads.ref_state(root)
                plain(root, row.example)
                self.assertEqual(shared_reads.ref_state(root), before, "a row that names a call which writes")

    def test_a_call_that_differs_from_a_row_by_one_word_is_a_write(self):
        """The mutations a hostile or careless caller makes: an option no row lists, an abbreviation, a count of arguments no row allows."""
        for row in git_forms.FORMS:
            name, words = row.example[0], list(row.example[1:])
            mutations = {"an unlisted option": [name, "--unlisted-option", *words], "an unknown subcommand": ["frobnicate", *words]}
            if not {"--", "--end-of-options"} & set(words):  # after one, git reads every word as an argument
                mutations["an option after the name"] = [name, *words, "--unlisted-option"]
            listed = [w for w in words if w.startswith("--") and "=" not in w and len(w) > 6]
            if listed:
                mutations["an abbreviated option"] = [name, *(w[:-2] if w == listed[0] else w for w in words)]
            if row.arguments[1] is not None:
                mutations["one argument too many"] = [name, *words, *["extra"] * (row.arguments[1] + 1)]
            for label, argv in mutations.items():
                with self.subTest(name=name, mutation=label):
                    self.assertTrue(git_calls.may_write(argv), f"{argv} is no row's form")
                    self.assertFalse(git_calls.kept_shape(argv))

    def test_a_call_with_no_subcommand_writes_nothing_and_an_empty_one_is_no_row(self):
        for argv in ([], ["--version"], ["-c", "a=b"]):
            with self.subTest(argv=argv):
                self.assertFalse(git_calls.may_write(argv))
                self.assertFalse(git_calls.kept_shape(argv))

    def test_a_global_option_before_the_subcommand_changes_no_class(self):
        for argv in (["-c", "core.abbrev=12", "rev-parse", "HEAD"], ["-C", "elsewhere", "symbolic-ref", "-q", "HEAD"]):
            with self.subTest(argv=argv):
                self.assertEqual(aidd_class(tuple(argv)), "kept")
        self.assertEqual(aidd_class(("-c", "core.abbrev=12", "branch", "x")), "write")


# The subcommand of each call a read or write the product issues, by its name: every one is a row of the table or named here, so
# a new call is classed on purpose. Only calls that pass a literal list are found (a list built elsewhere is not).
KNOWN_WRITES = {
    "checkout": "moves HEAD or the work tree",
    "check-ref-format": "reads a name only, and is kept a write for the form it takes (`@{-1}` reads the reflog)",
    "cherry": "reads commits, and is left a write: no scope reads it",
    "commit": "moves a branch",
    "commit-tree": "writes an object",
    "fetch": "writes refs and objects",
    "hash-object": "writes objects",
    "push": "writes refs on a remote",
    "stash": "stores a ref",
    "update-index": "writes the index",
    "update-ref": "writes a ref",
    "worktree": "adds, removes, or prunes a work tree",
    "write-tree": "writes an object",
}
GIT_CALLERS = {"run", "ok", "attempt", "_git"}


def literal_calls() -> list[tuple[str, int, list[str]]]:
    """(file, line, words) of each call of the product's git runner that passes a list; a word that is no literal is `x`."""
    found = []
    for path in sorted((helpers.ROOT / "src" / "aidd").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            func = node.func if isinstance(node, ast.Call) else None
            called = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
            if called in GIT_CALLERS and isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.List):
                words = [
                    e.value
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)
                    else "x.y"
                    if isinstance(e, ast.JoinedStr) and "." in ast.unparse(e)
                    else "x"
                    for e in node.args[0].elts
                ]
                if words[0] != "git" and git_calls.subcommand(words)[1] not in ("", "x"):  # `["git", ...]` is a program started by hand
                    found.append((str(path.relative_to(helpers.ROOT)), node.lineno, words))
    return found


class EveryCallTheProductIssuesIsClassedOnPurpose(unittest.TestCase):
    def test_each_literal_call_is_a_row_or_a_known_write(self):
        calls = literal_calls()
        self.assertGreater(len(calls), 60, "the control: the scan finds the product's calls")
        for where, line, words in calls:
            name = git_calls.subcommand(words)[1]
            with self.subTest(where=f"{where}:{line}", words=words):
                if git_calls.may_write(words):
                    self.assertIn(
                        name, KNOWN_WRITES, f"{name} is no row and no known write: add a row to git_forms, or name it in KNOWN_WRITES with the reason"
                    )

    def test_each_known_write_is_still_issued_and_is_a_write(self):
        issued = {git_calls.subcommand(words)[1]: words for _, _, words in literal_calls() if git_calls.may_write(words)}
        for name in KNOWN_WRITES:
            with self.subTest(name=name):
                self.assertIn(name, issued, "no call issues it any more: drop it from KNOWN_WRITES")


class NoScopeOutlivesACommand(unittest.TestCase):
    def test_each_command_ends_with_no_scope_open(self):
        """Every command a person runs leaves the process with no kept read."""
        with tempfile.TemporaryDirectory() as tmp:
            root = helpers.make_repo(Path(tmp).resolve() / "repo")
            for argv in (["risk", "--paths", "a.txt"], ["status"], ["doctor", "--json"], ["validate"], ["init", "--dry-run"], ["test", "--help"]):
                with self.subTest(argv=argv):
                    helpers.aidd_here(*argv, cwd=root)
                    self.assertIsNone(git_reads.current())


if __name__ == "__main__":
    unittest.main()
