"""Input an agent controls, reaching a parser: git log records, commit messages and author names, Spec bodies, TOML
nesting, and very large diffs. Fixed fields are read NUL-separated and free text by its length; size and depth are
capped; a parse failure stays with its file and never turns a check off; matching stays fast at monorepo scale."""

import collections
import contextlib
import io
import itertools
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import helpers
from helpers import git, make_repo, run_cli

from aidd import config
from aidd.workitems import spec_file
from aidd.kernel import documents, git_calls, globs
from aidd.kernel import git as gitutil
from aidd.kernel import git_reads

HAS_GIT = shutil.which("git") is not None
FORGED_SHA = "f" * 40


def repo_at(root: Path, email: str = "me@example.com") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    for k, v in (("user.email", email), ("user.name", "Me"), ("commit.gpgsign", "false")):
        git(root, "config", k, v)
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-qm", "day 0")
    return root


@unittest.skipUnless(HAS_GIT and os.name == "posix", "git and a POSIX shell are required")
class HostileRepositoryTests(unittest.TestCase):
    """S9: a repository you did not write, or an environment that names a program for git, cannot run code when aidd reads.
    Each class of program git can run: an fsmonitor, a clean filter, a textconv, an external diff, a hook, a pager."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.root = repo_at(self.dir / "repo")
        (self.root / ".gitattributes").write_text("* filter=evil diff=evil\n", encoding="utf-8")
        git(self.root, "add", ".gitattributes")
        git(self.root, "commit", "-qm", "attributes")
        os.utime(self.root / ".gitattributes", (1, 1))  # not what the index recorded, so git hashes it (a write in the same second would not)
        self.marker = self.dir / "ran"
        self.scripts = {name: self.script(name) for name in ("fsmonitor", "clean", "textconv", "external", "hook", "pager")}
        for key, name in (
            ("core.fsmonitor", "fsmonitor"),
            ("filter.evil.clean", "clean"),
            ("diff.evil.textconv", "textconv"),
            ("diff.external", "external"),
            ("core.pager", "pager"),
        ):
            git(self.root, "config", key, str(self.scripts[name]))
        (self.root / "a.txt").write_text("changed\n", encoding="utf-8")  # something for a status and a diff to read

    def script_text(self, name: str, ends: bool = False) -> str:
        if ends:  # a program git starts and waits on, such as ssh: it must end at once
            return f'#!/bin/sh\necho {name} >> "{self.marker}"\nexit 1\n'
        return f'#!/bin/sh\necho {name} >> "{self.marker}"\nif [ -n "$1" ] && [ -f "$1" ]; then cat "$1"; else cat; fi\nexit 0\n'

    def script(self, name: str, ends: bool = False) -> Path:
        return helpers.write_executable(self.dir / f"{name}.sh", self.script_text(name, ends))

    def ran(self) -> set[str]:
        seen = set(self.marker.read_text(encoding="utf-8").split()) if self.marker.exists() else set()
        self.marker.unlink(missing_ok=True)
        return seen

    def plain_git(self, *args: str) -> None:
        self.plain_git_in(self.root, *args)

    def plain_git_in(self, folder: Path, *args: str) -> None:
        subprocess.run(["git", *args], cwd=folder, capture_output=True, timeout=60, check=False, stdin=subprocess.DEVNULL)

    def test_a_hostile_repository_config_runs_nothing_on_aidds_reads(self):
        for args in (("status", "--porcelain"), ("diff", "HEAD"), ("diff", "--no-ext-diff", "HEAD")):
            self.plain_git(*args)
        self.assertEqual(self.ran(), {"fsmonitor", "clean", "textconv", "external"}, "the control: git itself runs each, so each can fire")
        root = str(self.root)
        self.assertIn("a.txt", gitutil.dirty(root))
        self.assertIn("a.txt", gitutil.run(["status", "--porcelain"], root))
        self.assertIn("+changed", gitutil.run(["diff", "HEAD", "--no-color"], root))
        self.assertIn("a.txt", gitutil.run(["diff", "--name-only", "HEAD"], root))
        self.assertIn("a.txt", gitutil.run(["ls-files", "-z", "--cached", "--others", "--exclude-standard"], root))
        self.assertTrue(gitutil.run(["log", "-p", "-1", "--no-color"], root))
        self.assertTrue(gitutil.run(["show", "HEAD"], root))
        self.assertEqual(self.ran(), set())

    def test_a_hostile_environment_runs_nothing_on_a_read_even_when_the_caller_passes_it(self):
        hostile = {**os.environ, "GIT_EXTERNAL_DIFF": str(self.scripts["external"]), "GIT_PAGER": str(self.scripts["pager"])}
        subprocess.run(["git", "diff"], cwd=self.root, env=hostile, capture_output=True, timeout=60, check=False, stdin=subprocess.DEVNULL)
        self.assertIn("external", self.ran(), "the control: git itself runs GIT_EXTERNAL_DIFF")
        with mock.patch.dict(os.environ, hostile):
            self.assertIn("+changed", gitutil.run(["diff", "HEAD", "--no-color"], str(self.root)))
        self.assertEqual(self.ran(), set())
        self.assertIn("+changed", gitutil.run(["diff", "HEAD", "--no-color"], str(self.root), env=hostile))  # the caller's own env too
        self.assertEqual(self.ran(), set())

    def test_a_repository_hook_does_not_run_on_a_checkout_aidd_makes(self):
        plain = repo_at(self.dir / "plain")  # without the config above, whose clean filter would also run on a stash
        hook = plain / ".git" / "hooks" / "post-checkout"
        helpers.write_executable(hook, self.script_text("hook"))
        git(plain, "checkout", "-q", "--detach", "HEAD")
        self.assertEqual(self.ran(), {"hook"}, "the control: git itself runs the post-checkout hook")
        gitutil.run(["checkout", "--quiet", "--detach", "HEAD"], str(plain))
        self.assertEqual(self.ran(), set())

    @unittest.skipIf(gitutil._version() < (2, 54), "git before 2.54 has no config-based hooks (hook.<name>.command), so there is none to run")
    def test_a_config_hook_a_tracked_file_includes_does_not_run_on_a_call_aidd_makes(self):
        """D-S2: git 2.54 and later run `hook.<name>.command` for `hook.<name>.event`, whatever `core.hooksPath` says. A
        tracked `.gitconfig` that the repository's config includes can name one, so aidd turns each off per call."""
        plain = repo_at(self.dir / "plain")
        events = ("post-checkout", "reference-transaction", "post-index-change")
        lines = [
            f'[hook "{name}"]\n\tcommand = {self.script(name)}\n' + "".join(f"\tevent = {event}\n" for event in events) for name in ("evil", "dotted.name=odd")
        ]
        (plain / ".gitconfig").write_text("".join(lines), encoding="utf-8")
        git(plain, "config", "include.path", "../.gitconfig")
        (plain / "a.txt").write_text("changed\n", encoding="utf-8")
        git(plain, "checkout", "-q", "--detach", "HEAD")
        self.assertEqual(self.ran(), {"evil", "dotted.name=odd"}, "the control: git itself runs a config hook, even beside core.hooksPath=/dev/null")
        for name, args in (
            ("checkout", ["checkout", "--quiet", "--detach", "HEAD"]),
            ("update-ref", ["update-ref", "refs/heads/made", "HEAD"]),
            ("symbolic-ref", ["symbolic-ref", "refs/heads/linked", "refs/heads/made"]),
            ("status", ["status", "--porcelain"]),
            ("branch", ["branch", "-q", "other"]),
        ):
            with self.subTest(call=name):
                gitutil.run(args, str(plain))
                self.assertEqual(self.ran(), set())
        with git_reads.shared_reads():  # the cache keeps no hook list across a write
            gitutil.run(["status", "--porcelain"], str(plain))
            gitutil.run(["checkout", "--quiet", "--detach", "HEAD"], str(plain))
            gitutil.run(["status", "--porcelain"], str(plain))
        self.assertEqual(self.ran(), set())
        # A diff over a file whose stat changed, and not its content, refreshes the index, which starts post-index-change.
        (plain / "b.txt").write_text("b\n", encoding="utf-8")
        git(plain, "add", "b.txt")
        git(plain, "commit", "-qm", "b")
        stamp = [2_000_000_000]

        def touch() -> None:
            stamp[0] += 100
            os.utime(plain / "b.txt", (stamp[0], stamp[0]))
            self.ran()

        touch()
        self.plain_git_in(plain, "diff", "--name-only")
        self.assertEqual(self.ran(), {"evil", "dotted.name=odd"}, "the control: git's own diff starts the hook on a stat-only change")
        for name, call in (
            ("diff", lambda: gitutil.run(["diff", "--name-only", "-z", "HEAD"], str(plain))),
            ("changed_since", lambda: gitutil.changed_since(str(plain), "HEAD")),
            ("numstat", lambda: gitutil.numstat("HEAD", None, str(plain))),
        ):
            with self.subTest(call=name):
                touch()
                call()
                self.assertEqual(self.ran(), set())

    def test_a_remote_update_and_a_remote_prune_start_hooks_so_only_the_read_forms_of_remote_and_config_skip_the_guard(self):
        """Review of D-S2: `remote update` fetches and `remote prune` deletes refs, so both start reference-transaction; a
        `remote add` or a `config` write changes what a later call reads. Only the exact read shapes aidd runs skip the guard."""
        starts = {
            ("remote", "update"): True,
            ("remote", "update", "origin"): True,
            ("remote", "prune", "origin"): True,
            ("remote", "add", "x", "y"): True,
            ("remote", "set-url", "origin", "z"): True,
            ("remote", "get-url", "--push", "-x"): True,
            ("config", "user.name", "x"): True,
            ("config", "core.probe", "--get"): True,
            ("config", "--unset", "user.name"): True,
            ("config", "--global", "user.name", "x"): True,
            ("status",): True,
            ("diff", "--name-only", "HEAD"): True,
            ("symbolic-ref", "HEAD", "refs/heads/x"): True,
            ("remote",): False,
            ("remote", "-v"): False,
            ("remote", "get-url", "origin"): False,
            ("remote", "get-url", "--push", "origin"): False,
            ("config", "user.name"): False,
            ("config", "--get", "user.name"): False,
            ("config", "--get-all", "user.name"): False,
            ("config", "--local", "--get", "user.name"): False,
            ("config", "--global", "--list"): False,
            ("config", "--list"): False,
            ("rev-list", "HEAD"): False,
            ("ls-remote", "origin"): False,
            ("rev-parse", "HEAD"): False,
        }
        for args, expected in starts.items():
            with self.subTest(args=args):
                self.assertEqual(git_calls.starts_hooks(list(args)), expected)

    def test_a_git_version_probe_that_times_out_is_asked_again(self):
        """Under load `git --version` can time out. Read as old and kept, it would drop `--attr-source` for as long as a
        long-running server lives. So an unknown git reads as new, every guard applies, and only a real answer is kept."""
        real = subprocess.run
        calls = {"n": 0}

        def slow_once(argv, *a, **kw):
            if argv[:2] == ["git", "--version"]:
                calls["n"] += 1
                if calls["n"] == 1:
                    raise subprocess.TimeoutExpired(argv, 10)
            return real(argv, *a, **kw)

        gitutil._version_seen.clear()
        try:
            with mock.patch.object(gitutil.subprocess, "run", side_effect=slow_once):
                self.assertEqual(gitutil._version(), (99, 0), "an unknown git reads as new, so every guard applies")
                self.assertLess(gitutil._version(), (99, 0), "and the next call asks git again")
        finally:
            gitutil._version_seen.clear()

    def test_a_call_counts_as_moving_refs_unless_it_is_a_known_shape_that_cannot(self):
        """A merge's names resolve before the line runs, so an earlier call that might move a ref makes them unknown. The
        list of calls that can't is short and closed: anything else, an alias or an unknown subcommand, counts as moving."""
        moves = {
            ("tag", "v1"): True,
            ("tag", "-l"): False,
            ("update-ref", "refs/remotes/origin/main", "abc"): True,
            ("branch", "-u", "origin/feat"): True,
            ("branch", "-a"): False,
            ("config", "branch.main.merge", "refs/heads/feat"): True,
            ("config", "--get", "user.name"): False,
            ("remote", "add", "x", "../x"): True,
            ("remote", "-v"): False,
            ("fetch",): True,
            ("fetch", "origin"): True,
            ("fetch", "--tags"): True,
            ("fetch", "--no-tags"): False,
            ("fetch", "--no-tags", "--tags"): True,
            ("fetch", "--tags", "--no-tags"): True,
            ("fetch", "--no-tags", "-t"): True,
            ("fetch", "--no-tags", "--tag"): True,
            ("fetch", "--no-tags", "--ta"): True,
            ("fetch", "--no-tags", "origin", "tag", "v1"): True,
            ("pull", "--no-tags", "tag", "v1"): True,
            ("fetch", "--no-tags", "--unknown-option"): True,
            ("fetch", "-t"): True,
            ("fetch", "--no-tags", "-q", "--prune", "origin"): False,
            ("pull", "--no-tags", "--ff-only", "origin", "main"): False,
            ("fetch", "--no-tags", "origin", "main"): True,
            ("fetch", "--no-tags", "origin", "feat:refs/remotes/origin/main"): True,
            ("fetch", "origin", "feat:refs/remotes/origin/main"): True,
            ("fetch", "--refmap=+refs/heads/*:refs/remotes/origin/*", "origin"): True,
            ("pull",): True,
            ("pull", "--no-tags"): False,
            ("pull", "origin", "feat:main"): True,
            ("push", ".", "feat:main"): True,
            ("push", "origin", "feat"): True,
            ("checkout", "-B", "main", "feat"): True,
            ("checkout", "feat"): False,
            ("switch", "-C", "main"): True,
            ("worktree", "add", "-B", "main", "../w"): True,
            ("reset", "--hard", "feat"): True,
            ("replace", "abc", "def"): True,
            ("-c", "remote.origin.fetch=+refs/heads/feat:refs/remotes/origin/main", "fetch"): True,
            ("-c", "alias.st=update-ref", "st"): True,
            ("st",): True,
            ("status",): False,
            ("log", "--oneline"): False,
            ("diff", "main"): False,
            ("add", "a.py"): False,
            ("commit", "-m", "x"): False,
            ("rev-parse", "HEAD"): False,
        }
        for args, expected in moves.items():
            with self.subTest(args=args):
                self.assertEqual(git_calls.moves_refs(list(args)), expected)

    @unittest.skipIf(gitutil._version() < (2, 54), "git before 2.54 has no config-based hooks (hook.<name>.command), so there is none to run")
    def test_a_config_hook_does_not_run_on_a_remote_update_or_prune_aidd_makes(self):
        origin = repo_at(self.dir / "origin-source")
        bare = self.dir / "bare.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(origin), str(bare)], check=True, capture_output=True)
        plain = self.dir / "plain"
        subprocess.run(["git", "clone", "-q", str(bare), str(plain)], check=True, capture_output=True)
        for name in ("gone1", "gone2"):
            git(bare, "branch", name, "main")
        git(plain, "fetch", "-q", "origin")
        for name in ("gone1", "gone2"):
            git(bare, "branch", "-D", name)
        for name in ("new1", "new2"):
            git(bare, "branch", name, "main")
        (plain / ".gitconfig").write_text(f'[hook "evil"]\n\tcommand = {self.script("evil")}\n\tevent = reference-transaction\n', encoding="utf-8")
        git(plain, "config", "include.path", "../.gitconfig")
        twin = self.dir / "twin"
        shutil.copytree(plain, twin, symlinks=True)
        for args in (("remote", "update", "origin"), ("remote", "prune", "origin")):
            self.plain_git_in(twin, *args)
        self.assertEqual(self.ran(), {"evil"}, "the control: git itself runs the config hook on both")
        gitutil.run(["remote", "update", "origin"], str(plain))
        gitutil.run(["remote", "prune", "origin"], str(plain))
        self.assertEqual(self.ran(), set())
        refs = git(plain, "for-each-ref", "--format=%(refname)", "refs/remotes/origin").split()
        self.assertIn("refs/remotes/origin/new1", refs, "the update did fetch")
        self.assertNotIn("refs/remotes/origin/gone1", refs, "and the prune did delete")

    def test_the_command_line_turns_every_handler_off(self):
        with mock.patch.object(gitutil, "_empty_tree", return_value="TREE"):
            local = gitutil._command(["status"], ".", remote=False)
            diff = gitutil._command(["-c", "core.quotepath=off", "diff", "-U0", "HEAD"], ".", remote=False)
            checkout = gitutil._command(["checkout", "--detach", "HEAD"], ".", remote=False)
            remote = gitutil._command(["ls-remote", "origin"], ".", remote=True)
        for setting in gitutil.SAFE_CONFIG + gitutil.LOCAL_CONFIG:
            self.assertIn(setting, local)
        self.assertEqual(local[:2], ["git", "--no-pager"])
        self.assertIn("--attr-source=TREE", local)
        self.assertLess(local.index("--no-optional-locks"), local.index("status"), "a status writes no index, so it starts no post-index-change hook")
        self.assertNotIn("--no-optional-locks", checkout)
        self.assertEqual(diff[diff.index("diff") + 1 : diff.index("diff") + 4], ["--no-ext-diff", "--no-textconv", "--ignore-submodules=dirty"])
        self.assertNotIn("--attr-source=TREE", checkout)  # a checkout needs the attributes (LFS, eol); it is named as unsafe
        self.assertIn("core.hooksPath=/dev/null", checkout)
        self.assertIn("core.fsmonitor=false", remote)  # a remote call runs no hook and no fsmonitor of its own repository
        self.assertIn("core.hooksPath=/dev/null", remote)
        self.assertIn("protocol.file.allow=user", remote)
        self.assertFalse(any(w in remote for w in gitutil.LOCAL_CONFIG), "a remote call keeps the person's ssh, credential, askpass, and proxy")
        self.assertFalse(any(w.startswith("--attr-source") for w in remote))
        self.assertEqual(remote[-2:], ["ls-remote", "origin"])

    def test_the_environment_drops_the_handler_variables_and_a_remote_call_keeps_the_person_ssh_and_askpass(self):
        hostile = {name: "/bin/evil" for name in gitutil.HANDLER_ENV} | {"KEEP": "1"}
        for call in (gitutil.GitCall(), gitutil.GitCall(env=hostile)):
            with mock.patch.dict(os.environ, hostile), self.subTest(env=call.env is not None):
                env = gitutil._environment(call)
                self.assertFalse(gitutil.HANDLER_ENV & set(env))
                self.assertEqual(env["KEEP"], "1")
        with mock.patch.dict(os.environ, hostile):
            env = gitutil._environment(gitutil.GitCall(env=dict(os.environ), remote=True))
        self.assertEqual({k for k in gitutil.HANDLER_ENV if k in env}, set(gitutil.REMOTE_ENV))
        self.assertEqual(env["GIT_SSH_COMMAND"], "/bin/evil")
        self.assertEqual(env["GIT_ASKPASS"], "/bin/evil")

    def test_the_callers_that_reach_a_remote_say_so(self):
        found = 0
        for module in ("aidd.records.sharing",):
            text = helpers.source_of(module)
            for call in re.finditer(r'git\.(?:run|attempt)\(\s*\["(?:ls-remote|fetch|push)"', text):
                found += 1
                self.assertIn("remote=True", text[call.start() : call.start() + 400], f"{module}: a call that reaches a remote opts in with remote=True")
        self.assertEqual(found, 2)  # the fetch and the push of the records
        # A public read of a release goes through git.ls_remote instead: a local call from a neutral folder.
        for module in ("aidd.setup.pins", "aidd.setup.self_updating"):
            self.assertNotRegex(helpers.source_of(module), r'git\.run\(\s*\["ls-remote"', module)

    def test_an_older_git_blanks_each_filter_the_repository_names_so_none_runs_on_a_read(self):
        git(self.root, "config", "filter.evil.process", str(self.scripts["clean"]))
        git(self.root, "config", "filter.evil.smudge", str(self.scripts["hook"]))
        git(self.root, "config", "filter.other.name.clean", str(self.scripts["pager"]))  # a name with a dot in it
        self.plain_git("status", "--porcelain")
        self.assertIn("clean", self.ran(), "the control: git itself runs the filter")
        for version in ((2, 39), (0, 0)):  # an old git, and one whose version could not be read
            gitutil._empty_tree.cache_clear()
            self.addCleanup(gitutil._empty_tree.cache_clear)
            with self.subTest(version=version), mock.patch.object(gitutil, "_version", return_value=version):
                command = gitutil._command(["status"], str(self.root), remote=False)
                self.assertFalse(any(w.startswith("--attr-source") for w in command))
                pairs = dict(gitutil._config_pairs(["status"], str(self.root), remote=False))
                for var in ("clean", "smudge", "process"):
                    self.assertEqual(pairs[f"filter.evil.{var}"], "")
                self.assertEqual(pairs["filter.other.name.clean"], "")
                self.assertIn("a.txt", gitutil.dirty(str(self.root)))
                self.assertIn("+changed", gitutil.run(["diff", "HEAD", "--no-color"], str(self.root)))
                self.assertEqual(self.ran(), set())

    def test_each_read_that_can_run_a_filter_blanks_them_and_runs_none(self):
        """Only the ref reads skip the filter probe, so every other read still blanks each filter, on an old git too."""
        git(self.root, "config", "filter.evil.smudge", str(self.scripts["clean"]))
        root, blob = str(self.root), "HEAD:a.txt"
        self.plain_git("cat-file", "--filters", blob)
        self.plain_git("hash-object", "a.txt")
        self.assertIn("clean", self.ran(), "the control: git itself runs a filter on a cat-file and a hash-object")
        reads = {
            "status": ["status", "--porcelain"],
            "diff": ["diff", "HEAD"],
            "log": ["log", "-p", "-1"],
            "show": ["show", blob],
            "grep": ["grep", "-n", "changed"],
            "ls-files": ["ls-files", "-m"],
            "cat-file": ["cat-file", "--filters", blob],
            "hash-object": ["hash-object", "a.txt"],
        }
        self.assertEqual(set(reads), gitutil.FILTER_READS, "a test for each read that can run a filter")
        for version in ((2, 55), (2, 39)):  # a git with --attr-source, and one without
            gitutil._empty_tree.cache_clear()
            self.addCleanup(gitutil._empty_tree.cache_clear)
            for name, args in reads.items():
                with self.subTest(version=version, read=name), mock.patch.object(gitutil, "_version", return_value=version):
                    self.assertEqual(dict(gitutil._config_pairs(args, root, remote=False))["filter.evil.clean"], "")
                    gitutil.run(args, root, check=False)
                    self.assertEqual(self.ran(), set())

    def test_a_ref_read_starts_no_filter_probe_and_runs_no_filter(self):
        """A read of refs, commits, or trees runs no filter even in plain git, so it skips the probe's process."""
        reads = {
            "ls-tree": ["ls-tree", "-r", "HEAD"],
            "rev-parse": ["rev-parse", "--verify", "HEAD^{commit}"],
            "symbolic-ref": ["symbolic-ref", "-q", "--short", "HEAD"],
            "for-each-ref": ["for-each-ref", "--format=%(refname) %(contents)", "refs/heads"],
            "merge-base": ["merge-base", "HEAD", "HEAD"],
        }
        self.assertEqual(set(reads), git_calls.REF_READS, "a test for each read that skips the probe")
        self.assertEqual(git_calls.REF_READS | git_calls.FILTER_READS, git_calls.EMPTY_ATTRIBUTES_COMMANDS)
        self.assertFalse(git_calls.REF_READS & git_calls.FILTER_READS)
        root = str(self.root)
        with mock.patch.object(gitutil, "_blank_pairs", side_effect=AssertionError("probed")), self.assertRaises(AssertionError):
            gitutil.run(["status", "--porcelain"], root)  # the control: the patch reaches the probe, which a read that can run a filter starts
        for name, args in reads.items():
            with self.subTest(read=name):
                self.plain_git(*args)
                self.assertEqual(self.ran(), set(), "the control: git itself runs nothing on this read")
                with mock.patch.object(gitutil, "_blank_pairs", side_effect=AssertionError("probed")):
                    self.assertTrue(gitutil.run(args, root).strip())
                self.assertEqual(self.ran(), set())

    def test_shared_reads_probe_the_filters_once_and_a_write_reads_them_afresh(self):
        """Inside `shared_reads`, each folder's filters and each ref read come from git once, until a write."""
        root = str(self.root)
        started: list[list[str]] = []
        real = subprocess.run

        def counted(argv, *args, **kwargs):
            started.append([w for w in argv if not w.startswith("-") and "=" not in w][1:3])
            return real(argv, *args, **kwargs)

        with mock.patch.object(gitutil.subprocess, "run", counted):
            with git_reads.shared_reads():
                for _ in range(3):
                    self.assertIn("a.txt", gitutil.dirty(root))
                    self.assertEqual(gitutil.run(["symbolic-ref", "-q", "--short", "HEAD"], root).strip(), "main")
                self.assertEqual(sum(w[:1] == ["config"] for w in started), 1, started)
                self.assertEqual(sum(w[:1] == ["symbolic-ref"] for w in started), 1, started)
                gitutil.run(["branch", "-q", "other"], root)  # a write: what came before may have changed
                self.assertIn("a.txt", gitutil.dirty(root))
                gitutil.run(["symbolic-ref", "-q", "--short", "HEAD"], root)
                self.assertEqual(sum(w[:1] == ["config"] for w in started), 2, started)
                self.assertEqual(sum(w[:1] == ["symbolic-ref"] for w in started), 2, started)
                for _ in range(2):  # a config get and a bare `git remote` are kept too; a config set is a write
                    gitutil.run(["config", "--get", "user.email"], root)
                    gitutil.run(["remote"], root)
                self.assertEqual(sum(w[:1] == ["config"] for w in started), 3, started)
                self.assertEqual(sum(w[:1] == ["remote"] for w in started), 1, started)
                gitutil.run(["config", "user.email", "you@example.com"], root)
                self.assertEqual(gitutil.run(["config", "--get", "user.email"], root).strip(), "you@example.com")
                head = ["symbolic-ref", "-q", "--short", "HEAD"]
                self.assertEqual(gitutil.run(head, root).strip(), "main")  # kept now, so only the write below can change the answer
                gitutil.run(["symbolic-ref", "HEAD", "refs/heads/other"], root)  # a symbolic-ref that sets one is a write
                self.assertEqual(gitutil.run(head, root).strip(), "other")
                gitutil.run(["symbolic-ref", "refs/heads/linked", "refs/heads/main"], root)
                linked = ["symbolic-ref", "-q", "--short", "refs/heads/linked"]
                self.assertEqual(gitutil.run(linked, root).strip(), "main")
                gitutil.run(["symbolic-ref", "-d", "refs/heads/linked"], root)  # and one that deletes it
                self.assertEqual(gitutil.run(linked, root, check=False).strip(), "")
            started.clear()
            self.assertIn("a.txt", gitutil.dirty(root))  # outside the scope, each read probes afresh
            self.assertIn("a.txt", gitutil.dirty(root))
            self.assertEqual(sum(w[:1] == ["config"] for w in started), 2, started)
        self.assertEqual(self.ran(), set())

    def test_a_signature_field_that_would_run_the_repositorys_gpg_program_is_refused(self):
        """D-S6: `%G?` and the other `%G` fields make git run `gpg.program` on a signed commit, so `log_fields` refuses them."""
        root = str(self.root)
        tree, parent = git(self.root, "rev-parse", "HEAD^{tree}"), git(self.root, "rev-parse", "HEAD")
        who = "Me <me@example.com> 1700000000 +0000"
        raw = f"tree {tree}\nparent {parent}\nauthor {who}\ncommitter {who}\ngpgsig -----BEGIN PGP SIGNATURE-----\n \n abc\n -----END PGP SIGNATURE-----\n\nsigned\n"
        signed = subprocess.run(
            ["git", "hash-object", "-t", "commit", "-w", "--stdin"], cwd=root, input=raw, capture_output=True, text=True, check=True
        ).stdout.strip()
        git(self.root, "config", "gpg.program", str(self.scripts["hook"]))
        self.plain_git("log", "-1", "--format=%G?", signed)
        self.assertEqual(self.ran(), {"hook"}, "the control: git itself runs gpg.program for a signature field")
        for field in ("%G?", "%GS", "%GK", "%GG", "%(signature)", "%+G?", "%-GS", "% GK", "%+(signature)"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                gitutil.log_fields([signed, "-1"], ["%H", field], root)
            self.assertEqual(self.ran(), set())
        self.assertEqual(gitutil.log_fields([signed, "-1"], ["%H", "%ae", "%%G"], root)[0][1:], ["me@example.com", "%G"], "a literal percent sign is no field")
        self.assertEqual(self.ran(), set())

    def test_shared_reads_keep_only_the_exact_shapes_aidd_reads_with(self):
        """D-S4: a `symbolic-ref -qd`, a `--del`, and a `config <name> --get` (which sets the value "--get") are writes."""
        root = str(self.root)
        git(self.root, "symbolic-ref", "refs/heads/linked", "refs/heads/main")
        linked = ["symbolic-ref", "-q", "--short", "refs/heads/linked"]
        value = ["config", "--get", "core.probe"]
        with git_reads.shared_reads():
            self.assertEqual(gitutil.run(linked, root).strip(), "main")
            self.assertEqual(gitutil.run(value, root, check=False).strip(), "")
            gitutil.run(["config", "core.probe", "--get"], root)
            self.assertEqual(gitutil.run(value, root).strip(), "--get", "git set the value, so the answer kept before it is gone")
            for delete in (["symbolic-ref", "-qd", "refs/heads/linked"], ["symbolic-ref", "--del", "refs/heads/linked"]):
                with self.subTest(delete=delete):
                    gitutil.run(["symbolic-ref", "refs/heads/linked", "refs/heads/main"], root)  # through aidd, so what was kept is dropped
                    self.assertEqual(gitutil.run(linked, root).strip(), "main")
                    gitutil.run(delete, root)
                    self.assertEqual(gitutil.run(linked, root, check=False).strip(), "")
        kept = [
            (["rev-parse", "HEAD"], True),
            (["ls-tree", "-r", "HEAD"], True),
            (["symbolic-ref", "-q", "--short", "HEAD"], True),
            (["symbolic-ref", "-q", "HEAD"], True),
            (["config", "--get", "user.name"], True),
            (["config", "--local", "--get", "user.name"], True),
            (["remote"], True),
            (["remote", "-v"], True),
            (["symbolic-ref", "HEAD", "refs/heads/x"], False),
            (["symbolic-ref", "-qd", "refs/x"], False),
            (["symbolic-ref", "--short", "-q", "HEAD"], True),
            (["symbolic-ref", "-q", "--short", "--delete"], False),
            (["config", "user.name", "--get"], False),
            (["config", "--get", "--add"], False),
            (["config", "--get-all", "user.name"], True),
            (["config", "--list"], True),
            (["remote", "add", "x", "y"], False),
            (["status"], False),
        ]
        for args, expected in kept:
            with self.subTest(args=args):
                self.assertEqual(git_calls.kept_shape(args), expected)
                self.assertEqual(
                    git_calls.may_write(args), not expected and args[0] != "status", "a kept shape writes nothing, and a read of the tree writes no ref"
                )

    def test_shared_reads_key_each_answer_by_the_folder_and_ignore_a_callers_environment(self):
        """D-L2: one scope serves two repositories and two worktrees, each from its own config and refs; a caller's own
        environment starts git again; and a call with none of those is answered once (the control)."""
        other = repo_at(self.dir / "other")
        git(self.root, "branch", "side")
        wt = self.dir / "wt"
        git(self.root, "worktree", "add", "-q", str(wt), "side")
        started: list[list[str]] = []
        real = subprocess.run

        def counted(argv, *args, **kwargs):
            started.append([w for w in argv if not w.startswith("-") and "=" not in w][1:2])
            return real(argv, *args, **kwargs)

        head = ["symbolic-ref", "-q", "--short", "HEAD"]
        gitutil.run(["rev-parse", "HEAD"], str(self.root))  # the object-format probe, kept for the folder, is not what this counts
        with mock.patch.object(gitutil.subprocess, "run", counted), git_reads.shared_reads():
            for _ in range(2):
                gitutil.run(["rev-parse", "HEAD"], str(self.root))
            self.assertEqual(started.count(["rev-parse"]), 1, "the control: the same read in the same folder is answered once")
            for _ in range(2):
                gitutil.run(["rev-parse", "HEAD"], str(self.root), env=dict(os.environ))
            self.assertEqual(started.count(["rev-parse"]), 3, "a caller's environment may change the answer, so each such call starts git")
            self.assertEqual(gitutil.run(head, str(self.root)).strip(), "main")
            self.assertEqual(gitutil.run(head, str(wt)).strip(), "side")
            started.clear()
            gitutil.dirty(str(other))  # the other repository has no filter, and this one has: each is probed on its own
            self.assertEqual(dict(gitutil._config_pairs(["status"], str(other), remote=False)), {})
            self.assertEqual(dict(gitutil._config_pairs(["status"], str(self.root), remote=False))["filter.evil.clean"], "")
            self.assertEqual(started.count(["config"]), 2, started)

    def test_every_read_that_can_run_a_filter_hands_git_the_blanks(self):
        """D-S5: `_git` puts the blanks in the environment of each read that can run a filter, though some of these reads
        run none in this fixture, so no marker file would show a call that left them out."""
        reads = {
            "status": ["status", "--porcelain"],
            "diff": ["diff", "HEAD"],
            "log": ["log", "-1"],
            "show": ["show", "HEAD:a.txt"],
            "grep": ["grep", "-n", "changed"],
            "ls-files": ["ls-files", "-m"],
            "cat-file": ["cat-file", "-p", "HEAD:a.txt"],
            "hash-object": ["hash-object", "a.txt"],
        }
        self.assertEqual(set(reads), gitutil.FILTER_READS)
        real = subprocess.run
        seen: list[dict[str, str]] = []

        def spying(argv, *args, **kwargs):
            if "config" not in argv and "--show-object-format" not in argv:  # not a probe
                seen.append(kwargs["env"])
            return real(argv, *args, **kwargs)

        for name, args in reads.items():
            seen.clear()
            with self.subTest(read=name), mock.patch.object(gitutil.subprocess, "run", spying):
                gitutil.run(args, str(self.root), check=False)
                [env] = seen
                keys = {env[f"GIT_CONFIG_KEY_{i}"]: env[f"GIT_CONFIG_VALUE_{i}"] for i in range(int(env["GIT_CONFIG_COUNT"]))}
                self.assertEqual(keys["filter.evil.clean"], "")
                self.assertEqual(keys["filter.evil.required"], "false")

    def test_an_older_git_that_cannot_list_the_filters_says_so_once_with_the_next_step(self):
        gitutil._empty_tree.cache_clear()
        self.addCleanup(gitutil._empty_tree.cache_clear)
        self.addCleanup(gitutil._SAID.clear)
        gitutil._SAID.clear()
        with mock.patch.object(gitutil, "_version", return_value=(2, 39)), mock.patch.object(gitutil, "_probe", return_value=None):
            with contextlib.redirect_stderr(io.StringIO()) as said:
                gitutil._config_pairs(["status"], str(self.root), remote=False)
                gitutil._config_pairs(["diff"], str(self.root), remote=False)
        lines = said.getvalue().splitlines()
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("Update git to 2.40 or later", lines[0])

    def test_the_neutral_environment_points_git_at_no_repository_or_config(self):
        hostile = {name: "/x" for name in gitutil.LOCATION_ENV} | {
            "GIT_CONFIG_KEY_0": "core.fsmonitor",
            "GIT_CONFIG_VALUE_0": "/x",
            "GIT_CONFIG_GLOBAL": "/g",
            "KEEP": "1",
        }
        with mock.patch.dict(os.environ, hostile):
            env = gitutil.neutral_env(self.dir)
        self.assertFalse(gitutil.LOCATION_ENV & set(env))
        self.assertFalse([k for k in env if k.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))])
        self.assertEqual((env["KEEP"], env["GIT_CONFIG_GLOBAL"], env["GIT_CEILING_DIRECTORIES"]), ("1", "/g", str(self.dir.parent)))

    def test_a_filter_chosen_by_info_attributes_does_not_run_on_a_read_on_any_git(self):
        """`--attr-source` skips the tree's attributes but not `.git/info/attributes`, so each filter the config names is blanked."""
        plain = repo_at(self.dir / "info")
        (plain / ".git" / "info").mkdir(exist_ok=True)
        (plain / ".git" / "info" / "attributes").write_text("* filter=evil\n", encoding="utf-8")
        git(plain, "config", "filter.evil.clean", str(self.scripts["clean"]))
        git(plain, "config", "filter.evil.smudge", str(self.scripts["hook"]))
        (plain / "a.txt").write_text("b\n", encoding="utf-8")  # as long as before, so git hashes the file (the clean filter) to tell
        self.plain_git_in(plain, "status", "--porcelain")
        self.assertIn("clean", self.ran(), "the control: git itself runs the filter")
        head = git(plain, "rev-parse", "HEAD")
        folder = str(plain)
        for version in ((2, 55), (2, 39)):  # a git with --attr-source, and one without
            gitutil._empty_tree.cache_clear()
            self.addCleanup(gitutil._empty_tree.cache_clear)
            with self.subTest(version=version), mock.patch.object(gitutil, "_version", return_value=version):
                self.assertIn("a.txt", gitutil.dirty(folder))
                self.assertTrue(gitutil.numstat(head, None, folder))
                self.assertIn("a.txt", gitutil.changed_since(folder, head))
                self.assertIn("+b", gitutil.run(["diff", "--no-color", head], folder))
                gitutil.run(["hash-object", "--stdin-paths"], folder, input="a.txt\n")
                self.assertEqual(self.ran(), set())

    def test_the_overrides_travel_in_the_environment_with_each_key_and_value_apart(self):
        env = gitutil._with_config(
            {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "a.b", "GIT_CONFIG_VALUE_0": "1"}, [("credential.https://x=y.helper", ""), ("core.sshcommand", "s=t")]
        )
        self.assertEqual(
            {k: v for k, v in env.items() if k.startswith("GIT_CONFIG")},
            {
                "GIT_CONFIG_COUNT": "3",
                "GIT_CONFIG_KEY_0": "a.b",
                "GIT_CONFIG_VALUE_0": "1",
                "GIT_CONFIG_KEY_1": "credential.https://x=y.helper",
                "GIT_CONFIG_VALUE_1": "",
                "GIT_CONFIG_KEY_2": "core.sshcommand",
                "GIT_CONFIG_VALUE_2": "s=t",
            },
        )
        self.assertEqual(gitutil._with_config({"GIT_CONFIG_COUNT": "x"}, [("a.b", "c")])["GIT_CONFIG_COUNT"], "1")

    def repo_with_submodule(self, name: str) -> Path:
        """A repository with a submodule whose own config names a clean filter that `.git/info/attributes` chooses, and a
        submodule file changed since the last commit, so a status or diff must hash it."""
        sub = repo_at(self.dir / f"{name}-sub")
        sup = repo_at(self.dir / name)
        git(sup, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "sub")
        git(sup, "commit", "-qm", "submodule")
        inner = sup / "sub"
        attributes = inner / git(inner, "rev-parse", "--git-path", "info/attributes")
        attributes.parent.mkdir(parents=True, exist_ok=True)
        attributes.write_text("* filter=evil\n", encoding="utf-8")
        git(inner, "config", "filter.evil.clean", str(self.scripts["clean"]))
        (inner / "a.txt").write_text("b\n", encoding="utf-8")
        os.utime(inner / "a.txt", (1, 1))  # not what the index recorded, so git hashes it
        return sup

    def test_a_filter_whose_name_holds_an_equals_sign_is_blanked_like_any_other(self):
        for number, name in enumerate(("evil", "x=y", "dotted.name")):
            with self.subTest(name=name):
                repo = repo_at(self.dir / f"named{number}")
                (repo / ".git" / "info").mkdir(exist_ok=True)
                (repo / ".git" / "info" / "attributes").write_text(f"* filter={name}\n", encoding="utf-8")
                git(repo, "config", f"filter.{name}.clean", str(self.scripts["clean"]))
                (repo / "a.txt").write_text("b\n", encoding="utf-8")
                os.utime(repo / "a.txt", (1, 1))
                self.plain_git_in(repo, "status", "--porcelain")
                self.assertIn("clean", self.ran(), "the control: git itself runs the filter")
                self.assertIn("a.txt", gitutil.dirty(str(repo)))
                self.assertEqual(self.ran(), set())

    def test_a_filter_setting_with_a_byte_that_is_not_utf8_never_stops_a_read(self):
        # A cp1252 path in a filter's value, or a byte in its name, once made every read fail on a UnicodeDecodeError.
        repo = repo_at(self.dir / "bytes")
        with (repo / ".git" / "config").open("ab") as fh:
            fh.write(b'[filter "lfs"]\n\tclean = C:/Users/Jos\xe9/lfs %f\n[filter "ev\xffil"]\n\tclean = ' + str(self.scripts["clean"]).encode() + b"\n")
        (repo / ".git" / "info").mkdir(exist_ok=True)
        (repo / ".git" / "info" / "attributes").write_bytes(b"* filter=ev\xffil\n")
        (repo / "a.txt").write_text("b\n", encoding="utf-8")
        os.utime(repo / "a.txt", (1, 1))
        self.plain_git_in(repo, "status", "--porcelain")
        self.assertIn("clean", self.ran(), "the control: git itself runs the filter")
        self.addCleanup(gitutil._SAID.clear)
        gitutil._SAID.clear()
        with contextlib.redirect_stderr(io.StringIO()) as said:
            self.assertIn("a.txt", gitutil.dirty(str(repo)))
        self.assertEqual(self.ran(), set())
        self.assertIn("aidd turns it off on its reads all the same", said.getvalue())
        self.assertIn("config --show-origin --get-regexp", said.getvalue())
        # Windows' environment can't carry the byte, so aidd can't turn that filter off there: it stops rather than read.
        with mock.patch.object(gitutil, "WINDOWS", True), self.assertRaises(gitutil.GitError) as stopped:
            gitutil._config_pairs(["status"], str(repo), remote=False)
        self.assertIn("config --show-origin --get-regexp", str(stopped.exception))

    def test_a_submodules_filter_does_not_run_on_a_read_even_when_the_repository_says_not_to_ignore_it(self):
        sup = self.repo_with_submodule("sup")
        git(sup, "config", "submodule.sub.ignore", "none")  # beats diff.ignoreSubmodules, so only the option stops it
        self.plain_git_in(sup, "status", "--porcelain")
        self.assertIn("clean", self.ran(), "the control: git itself enters the submodule and runs its filter")
        folder, head = str(sup), git(sup, "rev-parse", "HEAD")
        reads = {
            "dirty": lambda: gitutil.dirty(folder),
            "status": lambda: gitutil.run(["status", "--porcelain"], folder),
            "numstat": lambda: gitutil.numstat(head, None, folder),
            "changed_since": lambda: gitutil.changed_since(folder, head),
            "diff": lambda: gitutil.run(["diff", "--name-only", head], folder),
        }
        for name, read in reads.items():
            with self.subTest(read=name):
                read()
                self.assertEqual(self.ran(), set())

    def test_a_fetch_through_aidd_does_not_enter_a_submodule(self):
        sup = self.repo_with_submodule("recursing")
        bare = self.dir / "recursing.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, capture_output=True)
        git(sup, "remote", "add", "origin", str(bare))
        git(sup, "push", "-q", "origin", "HEAD:refs/heads/main")
        git(sup, "config", "fetch.recurseSubmodules", "true")
        git(sup / "sub", "config", "remote.origin.uploadpack", str(self.script("submodule-fetch", ends=True)))
        self.plain_git_in(sup, "fetch", "origin")
        self.assertIn("submodule-fetch", self.ran(), "the control: git itself fetches the submodule, which runs its own program")
        env = {**os.environ, **gitutil.FETCH_ENV}
        self.assertEqual(gitutil.attempt(["fetch", "origin"], str(sup), env, remote=True)[0], 0)
        self.assertEqual(self.ran(), set())

    def test_a_fetch_and_a_push_enter_no_submodule_whoever_calls_them(self):
        for remote, args in itertools.product((False, True), (["fetch", "origin"], ["push", "origin", "x"])):
            with self.subTest(remote=remote, command=args[0]):
                command = gitutil._command(args, ".", remote=remote)
                self.assertIn("--no-recurse-submodules" if args[0] == "fetch" else "--recurse-submodules=no", command)
        sup = self.repo_with_submodule("pushing")
        inner = sup / "sub"
        git(inner, "commit", "-qam", "newer")  # the superproject now points at a submodule commit no remote has
        git(sup, "add", "sub")
        git(sup, "commit", "-qm", "point at it")
        bare = self.dir / "pushing.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, capture_output=True)
        git(sup, "remote", "add", "origin", str(bare))
        git(sup, "config", "push.recurseSubmodules", "on-demand")
        git(inner, "config", "remote.origin.receivepack", str(self.script("submodule-push", ends=True)))
        self.ran()
        self.plain_git_in(sup, "push", "origin", "HEAD:refs/heads/main")
        self.assertIn("submodule-push", self.ran(), "the control: git itself pushes the submodule, which runs its own program")
        gitutil.attempt(["push", "origin", "HEAD:refs/heads/other"], str(sup), {**os.environ, **gitutil.FETCH_ENV}, remote=True)
        self.assertEqual(self.ran(), set())

    def test_the_alternate_refs_command_of_the_repository_does_not_run_on_a_fetch_through_aidd(self):
        repo = repo_at(self.dir / "alternates")
        other = repo_at(self.dir / "alternates-other")
        bare = self.dir / "alternates.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, capture_output=True)
        git(repo, "remote", "add", "origin", str(bare))
        git(repo, "push", "-q", "origin", "HEAD:refs/heads/main")
        (repo / ".git" / "objects" / "info" / "alternates").write_text(f"{other / '.git' / 'objects'}\n", encoding="utf-8")
        git(repo, "config", "core.alternateRefsCommand", str(self.script("alternates")))
        self.plain_git_in(repo, "fetch", "origin")
        self.assertIn("alternates", self.ran(), "the control: git itself runs the command to advertise the alternate's refs")
        self.assertEqual(gitutil.attempt(["fetch", "origin"], str(repo), {**os.environ, **gitutil.FETCH_ENV}, remote=True)[0], 0)
        self.assertEqual(self.ran(), set())

    def test_no_read_fetches_a_missing_object(self):
        """In a partial clone, a read of a missing blob fetches it from the promisor remote, which runs that remote's program."""
        bare = self.dir / "promisor.git"
        source = repo_at(self.dir / "promisor-source")
        subprocess.run(["git", "clone", "-q", "--bare", str(source), str(bare)], check=True, capture_output=True)
        git(bare, "config", "uploadpack.allowFilter", "true")
        partial = self.dir / "partial"
        made = subprocess.run(
            ["git", "-c", "protocol.file.allow=always", "clone", "-q", "--no-checkout", "--filter=blob:none", f"file://{bare}", str(partial)],
            capture_output=True,
            check=False,
        )
        if made.returncode != 0:
            self.skipTest("this git cannot make a partial clone")
        git(partial, "config", "remote.origin.uploadpack", str(self.script("lazy", ends=True)))
        git(partial, "config", "protocol.file.allow", "always")
        self.plain_git_in(partial, "show", "HEAD:a.txt")
        self.assertIn("lazy", self.ran(), "the control: git itself fetches the missing blob")
        gitutil.run(["show", "HEAD:a.txt"], str(partial), check=False)
        self.assertEqual(self.ran(), set())
        for env, remote in itertools.product((None, {"GIT_NO_LAZY_FETCH": "0"}), (False, True)):
            with self.subTest(env=env, remote=remote):
                self.assertEqual(gitutil._environment(gitutil.GitCall(env=env, remote=remote))["GIT_NO_LAZY_FETCH"], "1")

    def test_git_speaks_english_to_aidd_under_any_locale(self):
        # aidd reads some of git's messages to name the next step, so every git call runs with LC_ALL=C.
        german = {"LC_ALL": "de_DE.UTF-8", "LANG": "de_DE.UTF-8", "LANGUAGE": "de"}
        for remote in (False, True):
            with self.subTest(remote=remote):
                self.assertEqual(gitutil._environment(gitutil.GitCall(env=german, remote=remote))["LC_ALL"], "C")
        outside = self.dir / "no-repository"
        outside.mkdir()
        said = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=outside, env={**os.environ, **german}, capture_output=True, text=True, check=False)
        if "not a git repository" in said.stderr:
            self.skipTest("this git has no German messages")
        with mock.patch.dict(os.environ, german), self.assertRaisesRegex(gitutil.GitError, "not a git repository"):
            gitutil.run(["rev-parse", "--git-dir"], str(outside))

    def test_a_sha256_repository_still_reads(self):
        wide = self.dir / "wide"
        wide.mkdir()
        made = subprocess.run(["git", "init", "-q", "--object-format=sha256", str(wide)], capture_output=True, check=False)
        if made.returncode != 0:
            self.skipTest("this git has no sha256 repositories")
        self.assertEqual(gitutil._empty_tree(str(wide)), gitutil.EMPTY_TREE["sha256"])
        self.assertEqual(gitutil.run(["status", "--porcelain"], str(wide)), "")

    def test_ls_remote_runs_outside_the_repository_as_a_local_https_only_call(self):
        folder = self.dir / "neutral"
        folder.mkdir()
        with mock.patch.object(gitutil, "run", return_value="") as run:
            gitutil.ls_remote("https://example.test/r.git", ["refs/tags/v*"], folder, 5)
        args, cwd = run.call_args.args[:2]
        self.assertEqual(args[: len(gitutil.HTTPS_ONLY)], list(gitutil.HTTPS_ONLY))
        self.assertEqual(args[len(gitutil.HTTPS_ONLY) :][:1], ["ls-remote"])
        for name in ("http", "ssh", "git", "file", "ext"):  # a repository's own protocol.<name>.allow=always would beat protocol.allow
            self.assertIn(f"protocol.{name}.allow=never", args)
        self.assertEqual(cwd, str(folder))
        self.assertEqual(run.call_args.kwargs["env"]["GIT_CEILING_DIRECTORIES"], str(folder.parent))
        self.assertNotIn("remote", run.call_args.kwargs)  # a local call: no ssh, askpass, or credential program
        command = gitutil._command(args, cwd, remote=False)
        for setting in gitutil.LOCAL_CONFIG:
            self.assertIn(setting, command)

    def test_the_pin_check_reads_no_repository_config(self):
        from aidd.setup import pins

        with mock.patch.object(pins.resources, "cache_home", return_value=self.dir / "cache"), mock.patch.object(gitutil, "run", return_value="") as run:
            before = os.getcwd()
            os.chdir(self.root)
            self.addCleanup(os.chdir, before)
            pins.remote_refs()
        self.assertEqual(run.call_args.args[1], str(self.dir / "cache" / "self-update"))
        self.assertNotEqual(Path(run.call_args.args[1]).resolve(), self.root.resolve())


@unittest.skipUnless(HAS_GIT, "git is required")
class CommitRecordTests(unittest.TestCase):
    """C-03: a commit message or an author name cannot add a commit, an identity, or crash the reader."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = repo_at(Path(tmp.name))
        self.base = git(self.root, "rev-parse", "HEAD")

    def commit(self, message: str, *, name: str = "Me", path: str = "b.txt") -> str:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(message[:10] + str(time.monotonic()), encoding="utf-8")
        git(self.root, "add", ".")
        env = {**os.environ, "GIT_AUTHOR_NAME": name, "GIT_COMMITTER_NAME": name}
        subprocess.run(["git", "commit", "-q", "-F", "-"], cwd=self.root, input=message, text=True, encoding="utf-8", env=env, check=True)
        return git(self.root, "rev-parse", "HEAD")

    def test_a_message_adds_no_commit_and_no_identity(self):
        message = f"subject\n\nbody\x1e{FORGED_SHA}\x1fevil@x.io\x1fevil@x.io\x1f\x1fforged\nAssisted-by: none"
        sha = self.commit(message)
        found = gitutil.commits(self.base, "HEAD", str(self.root))
        self.assertEqual([c["sha"] for c in found], [sha])
        self.assertEqual((found[0]["author"], found[0]["committer"]), ("email:me@example.com", "email:me@example.com"))
        self.assertEqual(found[0]["message"], message)

    def test_a_short_record_does_not_crash_the_reader(self):
        # The old reader unpacked five fields from every record, so a message with a bare separator raised ValueError.
        sha = self.commit("subject\n\n\x1e\x1f\nmore")
        self.assertEqual([c["sha"] for c in gitutil.commits(self.base, "HEAD", str(self.root))], [sha])

    def test_a_carriage_return_and_crlf_in_a_message_read_as_text_mode_would(self):
        self.commit("subject\r\n\r\nbody\r\nAssisted-by: claude-code/x")
        self.assertEqual(gitutil.commits(self.base, "HEAD", str(self.root))[0]["message"], "subject\n\nbody\nAssisted-by: claude-code/x")


@unittest.skipUnless(HAS_GIT, "git is required")
class GitOutputTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = repo_at(Path(tmp.name))

    @unittest.skipIf(os.name == "nt", "Windows file names cannot hold a carriage return")
    def test_z_output_keeps_a_carriage_return_in_a_name(self):
        # C-07: universal newlines turned `a\rb.txt` into `a\nb.txt`, a path that does not exist.
        (self.root / "a\rb.txt").write_text("x\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "cr")
        self.assertIn("a\rb.txt", gitutil.ls_tree("HEAD", str(self.root)))
        self.assertIn("a\rb.txt", gitutil.dirty(str(self.root), untracked=True, check=False) + ["a\rb.txt"])
        self.assertEqual(gitutil.run(["log", "-1", "--format=%s"], str(self.root)).strip(), "cr")


class SpecSizeTests(unittest.TestCase):
    """C-04: a document has a size cap."""

    def test_a_document_past_the_cap_is_a_model_error(self):
        spec = "---\ntype: spec\nid: S-1\n---\n" + "x" * documents.MAX_DOCUMENT_BYTES
        for read in (documents.split_front_matter, lambda t, w: spec_file.load_object(t, w)):
            with self.assertRaises(documents.DocumentError) as err:
                read(spec, "specs/S-1.md")
            self.assertIn("at most", str(err.exception))
        # Multi-byte text counts in bytes, as a file on disk does.
        with self.assertRaises(documents.DocumentError):
            documents.split_front_matter("---\ntype: spec\n---\n" + "é" * (documents.MAX_DOCUMENT_BYTES // 2 + 1), "x")


DEEP = "a: " + "[" * 5000 + "]" * 5000 + "\n"


class NestingTests(unittest.TestCase):
    """C-05: deep YAML is a DocumentError naming the file, not a RecursionError."""

    def test_deep_yaml_is_a_document_error_naming_the_file(self):
        block = "".join(" " * i + f"k{i}:\n" for i in range(40)) + " " * 40 + "v: 1\n"
        for text in (DEEP, "a: " + "{b: " * 3000 + "1" + "}" * 3000 + "\n", "a: " + "[" * 40 + "]" * 40 + "\n", block):
            with self.assertRaises(documents.DocumentError) as err:
                documents.parse_yaml(text, "specs/S-9.md")
            self.assertIn("specs/S-9.md", str(err.exception))
            self.assertIn("nest more than", str(err.exception))
        self.assertEqual(documents.parse_yaml("a: " + "[" * 10 + "]" * 10, "x")["a"], [[[[[[[[[[]]]]]]]]]])

    def test_a_config_too_deep_is_a_config_error(self):
        with self.assertRaises((config.ConfigError, documents.DocumentError)):
            config.load_text('aidd_version: "1.0.0"\nprofile: team\n' + DEEP)


@unittest.skipUnless(HAS_GIT, "git is required")
class MalformedSpecIsolationTests(unittest.TestCase):
    """C-05: one Spec that cannot parse leaves the others read, and never opens a path in an area."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_repo(Path(tmp.name).resolve() / "r", spec="02-normal-feature:specs/SPEC-220.md")
        (self.root / "specs" / "SPEC-BAD.md").write_text("---\ntype: spec\nid: SPEC-BAD\n" + DEEP + "---\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "two Specs, one unreadable")

    def test_status_reads_the_other_specs(self):
        with contextlib.chdir(self.root):
            code, out = run_cli("status", "--json")
            self.assertEqual(code, 0, out)
            self.assertIn("SPEC-220", out)
            self.assertEqual([u["path"] for u in json.loads(out)["unreadable"]], ["specs/SPEC-BAD.md"])  # named, never dropped


class ScaleTests(unittest.TestCase):
    """C-06: a 20,000-file diff is judged in seconds (a 50,000-file one took 111 s)."""

    def test_the_prefilters_never_change_a_match(self):
        rnd = random.Random(11)
        atoms = ["a", "b", "/", "*", "**", "**/", "?", ".py", "src", "A", "x/"]
        for _ in range(4000):
            pattern = "".join(rnd.choice(atoms) for _ in range(rnd.randint(1, 6)))
            path = "".join(rnd.choice(["a", "b", "/", ".py", "src", "A", "x"]) for _ in range(rnd.randint(1, 8)))
            for fold in (False, True):
                c = globs._compile(pattern, fold)
                s = globs._folded(path) if fold else path
                self.assertEqual(globs.match(pattern, path, fold), globs._walk(c.tokens, c.prefix_match, s), (pattern, path, fold))


class SecretPatternWork(unittest.TestCase):
    """A secret pattern bounds its work on hostile text: no repeat runs again over the rest of a line on each retry. The password in
    a URL has no cap on its length (its look-ahead finds the `@` once from the colon), so lines built to make it rescan stay linear."""

    def test_a_url_password_pattern_reads_a_hostile_megabyte_in_linear_time(self):
        from aidd.kernel import secret_patterns

        rx = dict(secret_patterns.LOOSE_PATTERNS)["a password in a URL"]
        hostile = {
            "a password that never ends in `@`": "postgres://app:" + "x" * 1_000_000,
            "a scheme, a user, and a colon over and over": "a.b-c+d.e://u:" * 70_000,
            "a colon after a colon": "x://" + "u:" * 500_000,
            "a capped user, then a long password, many times": ("a://" + "b" * 199 + ":" + "p" * 300 + " ") * 3000,
            "a megabyte with no secret": "x" * 1_000_000,
        }
        for name, text in hostile.items():
            with self.subTest(name):
                started = time.monotonic()
                list(rx.finditer(text))
                self.assertLess(time.monotonic() - started, 2, "a rescan on each retry costs minutes on a megabyte")


class DeadCodeTests(unittest.TestCase):
    """C-16: every module-level function in src/aidd is used by src/aidd, beyond a door that lists it; a helper only tests use lives in tests/helpers.py."""

    def test_no_function_is_unused(self):
        src = Path(__file__).resolve().parent.parent / "src" / "aidd"
        texts = {p: p.read_text(encoding="utf-8") for p in src.rglob("*.py")}
        # A package door only lists names (aidd.kernel.doors), so a name only a door lists is unused too.
        everything = "\n".join(t for p, t in texts.items() if not (p.name == "__init__.py" and "__getattr__" in t))
        words = collections.Counter(re.findall(r"\w+", everything))  # one pass; a scan for each name was quadratic
        unused = [f"{p.name}:{name}" for p, text in texts.items() for name in re.findall(r"^def (\w+)\(", text, re.M) if words[name] <= 1]
        self.assertEqual(unused, [])

    def test_no_module_constant_is_unused(self):
        """A module-level name nothing reads is dead too. A constant only tests read still counts: it is a fact the
        tests hold the docs to, such as the Spec keys a hash leaves out."""
        root = Path(__file__).resolve().parent.parent
        texts = {p: p.read_text(encoding="utf-8") for p in (root / "src" / "aidd").rglob("*.py")}
        readers = [t for p, t in texts.items() if not (p.name == "__init__.py" and "__getattr__" in t)]
        readers += [p.read_text(encoding="utf-8") for p in (root / "tests").glob("*.py")]
        words = collections.Counter(re.findall(r"\w+", "\n".join(readers)))
        assigned = r"^([A-Za-z_]\w*)\s*(?::[^=\n]+)?=(?!=)"
        unused = [
            f"{p.name}:{name}"
            for p, text in texts.items()
            if not (p.name == "__init__.py" and "__getattr__" in text)
            for name in re.findall(assigned, text, re.M)
            if not name.startswith("__") and words[name] <= 1
        ]
        self.assertEqual(unused, [])


if __name__ == "__main__":
    unittest.main()
