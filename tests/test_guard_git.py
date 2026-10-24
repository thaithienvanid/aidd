"""The guard runs a working system git with a fixed environment, and the repository's fsmonitor, hooks, and driver programs do not run through it.

A project's settings can put a folder first on PATH or set any environment variable, and a repository's own
`.git/config` can name programs that git runs (core.fsmonitor, a filter or diff driver). Inside
`gitutil.system_only()` (the hook path), git comes from a fixed list of system paths that pass `git --version`,
runs with only an allowlisted environment, and has every program setting in config turned off. In a repository that
has adopted aidd, a git that cannot run there is a deny, never "no repository". Every other command keeps the git on
PATH.
"""

import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import git, make_repo

from aidd.guard import pre_tool
from aidd.guard import denial_log
from aidd.kernel import git as gitutil

COMMIT = ["-c", "user.name=x", "-c", "user.email=x@x", "commit", "-qm"]


@unittest.skipIf(os.name == "nt", "the fake git is a POSIX shell script")
@unittest.skipUnless(gitutil.system_git(), "no working git at a system path")
class GuardGitTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.base = base
        self.root = make_repo(base / "repo", branch=None)
        self.other = base / "other"
        self.other.mkdir()
        git(self.other, "init", "-q")
        self.marker = base / "fake-git-ran"
        self.fake_bin = base / "fake-bin"
        self.fake_bin.mkdir()
        self.script(self.fake_bin / "git", f"echo ran >> {self.marker}\necho {self.other}\nexit 0")
        self.path = os.pathsep.join([str(self.fake_bin), os.environ.get("PATH", "")])

    def script(self, path: Path, body: str) -> Path:
        path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        path.chmod(0o755)
        return path

    def edit_event(self, rel: str, root: Path | None = None) -> str:
        root = root or self.root
        return json.dumps({"tool_name": "Edit", "cwd": str(root), "tool_input": {"file_path": str(root / rel)}})

    def hook(self, event: str) -> dict | None:
        out = io.StringIO()
        self.assertEqual(pre_tool.pre_tool_hook(io.StringIO(event), out), 0)
        return json.loads(out.getvalue())["hookSpecificOutput"] if out.getvalue() else None

    def assert_git_deny(self, decision: dict | None) -> str:
        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual(decision["permissionDecision"], "deny")
        reason = decision["permissionDecisionReason"]
        self.assertEqual(denial_log.reason_code(reason), "guard_failed", reason)
        return reason

    def test_a_fake_git_first_on_path_is_not_run(self):
        with mock.patch.dict(os.environ, {"PATH": self.path}):
            with gitutil.system_only():
                self.assertEqual(Path(gitutil.toplevel(str(self.root))), self.root)
            self.assertFalse(self.marker.exists(), "the fake git ran inside system_only")
            # Every other command keeps the git on PATH: the gate, `aidd test`, and CI name theirs that way.
            self.assertEqual(Path(gitutil.toplevel(str(self.root))), self.other)
            self.assertTrue(self.marker.exists())

    def test_git_dir_and_the_other_git_variables_are_ignored(self):
        moved = {"GIT_DIR": str(self.other / ".git"), "GIT_WORK_TREE": str(self.other)}
        with mock.patch.dict(os.environ, moved):
            self.assertEqual(Path(gitutil.toplevel(str(self.root))), self.other)  # what they would do unchecked
            with gitutil.system_only():
                self.assertEqual(Path(gitutil.toplevel(str(self.root))), self.root)

    def test_the_hook_denies_with_a_fake_git_and_a_moved_git_dir(self):
        moved = {"PATH": self.path, "GIT_DIR": str(self.other / ".git"), "GIT_WORK_TREE": str(self.other)}
        with mock.patch.dict(os.environ, moved):
            decision = self.hook(self.edit_event(".aidd/config.yaml"))
        self.assertIsNotNone(decision)
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("protected path", decision["permissionDecisionReason"])
        self.assertFalse(self.marker.exists(), "the guard ran the fake git")

    def test_with_no_system_git_the_hook_denies_in_an_aidd_repository(self):
        missing = (str(self.root / "no" / "git"),)
        with mock.patch.object(gitutil, "SYSTEM_GITS", missing), mock.patch.dict(os.environ, {"PATH": self.path}):
            self.assertIsNone(gitutil.system_git())
            reason = self.assert_git_deny(self.hook(self.edit_event("src/app.py")))
            self.assertIn(missing[0], reason)
            self.assertIn("PATH", reason)
            # A shell command is denied the same way.
            bash = json.dumps({"tool_name": "Bash", "cwd": str(self.root / ".aidd"), "tool_input": {"command": "ls"}})
            self.assert_git_deny(self.hook(bash))
            # Outside an aidd repository the guard does not act, with or without git.
            self.assertIsNone(self.hook(self.edit_event("x.py", self.other)))
            with gitutil.system_only(), self.assertRaises(gitutil.GitError) as caught:
                gitutil.toplevel(str(self.root))
            self.assertIn(missing[0], str(caught.exception))
        self.assertFalse(self.marker.exists(), "the guard fell back to the git on PATH")

    def test_a_git_that_fails_its_version_check_is_never_chosen(self):
        # As the macOS /usr/bin/git shim without the Command Line Tools: executable, but every call fails.
        broken = self.script(self.base / "broken-git", f"echo ran >> {self.marker}\nexit 1")
        real = gitutil.system_git()
        with mock.patch.object(gitutil, "SYSTEM_GITS", (str(broken), real)):
            self.assertEqual(gitutil.system_git(), real)
        with mock.patch.object(gitutil, "SYSTEM_GITS", (str(broken),)):
            self.assertIsNone(gitutil.system_git())
            reason = self.assert_git_deny(self.hook(self.edit_event("src/app.py")))
            self.assertIn(str(broken), reason)
            self.assertIsNone(self.hook(self.edit_event("x.py", self.other)))  # outside aidd: allow, as before
        self.assertEqual(self.marker.read_text(encoding="utf-8").count("ran"), 1, "the version check runs once a process")

    def test_a_git_failure_in_an_aidd_repository_is_a_deny_not_no_repository(self):
        # A repository git cannot read (here a broken HEAD; a "dubious ownership" refusal reads the same way): the
        # guard never takes the failure for "no repository" and allows.
        (self.root / ".git" / "HEAD").write_text("garbage\n", encoding="utf-8")
        with gitutil.system_only():
            self.assertEqual(gitutil.toplevel(str(self.root)), "")
        reason = self.assert_git_deny(self.hook(self.edit_event("src/app.py")))
        self.assertIn("git", reason)
        # A folder with an aidd config and no repository at all is not one git failed to read.
        (self.base / "plain" / ".aidd").mkdir(parents=True)
        (self.base / "plain" / ".aidd" / "config.yaml").write_text("", encoding="utf-8")
        self.assertIsNone(self.hook(self.edit_event("x.py", self.base / "plain")))

    def test_repository_config_cannot_run_programs_through_the_guard(self):
        ran = self.base / "config-ran"
        fsmonitor = self.script(self.base / "fsmonitor", f"echo fsmonitor >> {ran}\nexit 1")
        clean = self.script(self.base / "clean", f"echo filter >> {ran}\ncat")
        (self.root / ".gitattributes").write_text("*.py filter=evil\n", encoding="utf-8")
        (self.root / "app.py").write_text("a = 1\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "-c", "user.name=x", "-c", "user.email=x@x", "commit", "-qm", "app")
        for key, value in (("core.fsmonitor", fsmonitor), ("filter.evil.clean", clean), ("filter.evil.process", clean)):
            git(self.root, "config", key, str(value))
        (self.root / "app.py").write_text("a = 2\n", encoding="utf-8")
        with gitutil.system_only():
            self.assertIn("app.py", gitutil.dirty(str(self.root), untracked=True))
            self.assertIn("app.py", gitutil.changed_since(str(self.root), "HEAD"))
            gitutil.hash_files(["app.py"], str(self.root))
        self.hook(self.edit_event("app.py"))
        self.assertFalse(ran.exists(), ran.read_text(encoding="utf-8") if ran.exists() else "")
        # The same calls outside system_only do run them: the setup is real.
        gitutil.dirty(str(self.root), untracked=True)
        self.assertTrue(ran.exists())

    def test_only_the_allowlisted_environment_reaches_git(self):
        planted = self.base / "planted"
        planted.mkdir()
        self.script(planted / "git-envdump", "env")
        session = {"PATH": os.pathsep.join([str(planted), os.environ.get("PATH", "")]), "PYTHONPATH": "/tmp/evil", "AIDD_PROBE": "session", "LANG": "C.UTF-8"}
        with mock.patch.dict(os.environ, session):
            self.assertIn("AIDD_PROBE=session", gitutil.run(["envdump"], str(self.root)))  # unchecked, PATH supplies it
        # A preloaded library would load into an unchecked git (and, missing, stops it); system_only drops it.
        hostile = {
            "LD_PRELOAD": "/tmp/evil.so",
            "DYLD_INSERT_LIBRARIES": "/tmp/evil.dylib",
            "GIT_DIR": "/tmp/evil",
            "GIT_CONFIG_PARAMETERS": "'core.fsmonitor=/tmp/evil'",
        }
        with mock.patch.dict(os.environ, session | hostile):
            with gitutil.system_only():
                with self.assertRaises(gitutil.GitError):
                    gitutil.run(["envdump"], str(self.root))  # the session's PATH no longer supplies git-* helpers
                dump = gitutil.run(["-c", "alias.envdump=!env", "envdump"], str(self.root))
        env = dict(line.split("=", 1) for line in dump.splitlines() if "=" in line)
        for name in ("LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "PYTHONPATH", "AIDD_PROBE", "GIT_DIR", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM"):
            self.assertNotIn(name, env)
        self.assertNotIn("/tmp/evil", env.get("GIT_CONFIG_PARAMETERS", ""))  # git's own, for the alias's `-c`
        # The overrides travel as GIT_CONFIG_COUNT/KEY/VALUE, which git never splits on `=`.
        count = int(env["GIT_CONFIG_COUNT"])
        pairs = {env[f"GIT_CONFIG_KEY_{i}"]: env[f"GIT_CONFIG_VALUE_{i}"] for i in range(count)}
        self.assertEqual(pairs["core.fsmonitor"], "false")
        self.assertNotIn(str(planted), env["PATH"])
        system = gitutil.system_git()
        assert system is not None
        self.assertTrue(env["PATH"].endswith(os.pathsep.join(["/usr/bin", "/bin", "/usr/sbin", "/sbin", os.path.dirname(system)])), env["PATH"])
        self.assertEqual(env["LANG"], "C.UTF-8")
        self.assertEqual(env.get("HOME"), os.environ.get("HOME"))

    def test_the_system_list_is_fixed_absolute_paths(self):
        expected = ("/opt/homebrew/bin/git", "/usr/local/bin/git", "/usr/bin/git", "/run/current-system/sw/bin/git", "/nix/var/nix/profiles/default/bin/git")
        self.assertEqual(gitutil.SYSTEM_GITS, expected)
        self.assertIn(gitutil.system_git(), gitutil.SYSTEM_GITS)

    @unittest.skipUnless(sys.platform == "darwin", "the Command Line Tools shim is macOS only")
    def test_the_macos_shim_is_skipped_without_the_command_line_tools(self):
        failed = mock.Mock(returncode=2)
        with mock.patch.object(gitutil, "SYSTEM_GITS", ("/usr/bin/git",)), mock.patch.dict(gitutil._WORKS, clear=True):
            with mock.patch.object(gitutil.subprocess, "run", return_value=failed) as run:
                self.assertIsNone(gitutil.system_git())
            (call,) = run.call_args_list  # xcode-select only: `/usr/bin/git --version` would open the install dialog
            self.assertEqual(call.args[0], ["/usr/bin/xcode-select", "-p"])


@unittest.skipIf(os.name == "nt", "the scripts are POSIX shell scripts")
@unittest.skipUnless(gitutil.system_git(), "no working git at a system path")
class RepositoryConfigOnlyTests(unittest.TestCase):
    """Only the repository's own config (`.git/config`, the worktree config, and what they include, or a config file
    inside the repository) is the threat. The user's global and the system config stay in force: safe.directory,
    core.excludesFile, and a global filter such as Git LFS."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.root = make_repo(self.base / "repo", branch=None)
        self.home = self.base / "home"
        self.home.mkdir()

    def script(self, name: str, body: str) -> Path:
        path = self.base / name
        path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        path.chmod(0o755)
        return path

    def filter_script(self, name: str) -> tuple[Path, Path]:
        marker = self.base / f"{name}-ran"
        return self.script(f"{name}.sh", f"echo ran >> {marker}\ncat"), marker

    def commit(self, files: dict[str, str], attributes: str) -> None:
        (self.root / ".gitattributes").write_text(attributes, encoding="utf-8")
        for rel, text in files.items():
            (self.root / rel).write_text(text, encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, *COMMIT, "files")
        for rel, text in files.items():
            (self.root / rel).write_text(text + "changed\n", encoding="utf-8")

    def global_config(self, text: str, home: Path | None = None) -> dict[str, str]:
        home = home or self.home
        (home / ".gitconfig").write_text(text, encoding="utf-8")
        return {"HOME": str(home)}

    def test_a_global_filter_stays_and_a_local_one_is_turned_off(self):
        glob_clean, glob_ran = self.filter_script("glob")
        local_clean, local_ran = self.filter_script("local")
        self.commit({"a.py": "a\n", "b.txt": "b\n"}, "*.py filter=glob\n*.txt filter=loc\n")
        git(self.root, "config", "filter.loc.clean", str(local_clean))
        with mock.patch.dict(os.environ, self.global_config(f'[filter "glob"]\n\tclean = {glob_clean}\n')):
            with gitutil.system_only():
                self.assertEqual(set(gitutil.dirty(str(self.root))), {"a.py", "b.txt"})
                gitutil.hash_files(["a.py", "b.txt"], str(self.root))  # runs each clean filter that is in force
                keys = dict(gitutil._system_overrides(gitutil.system_git(), str(self.root), {}))
        self.assertTrue(glob_ran.exists(), "the global filter (as Git LFS sets one) was turned off")
        self.assertFalse(local_ran.exists(), "the repository's own filter ran")
        self.assertEqual(keys.get("filter.loc.clean"), "")
        self.assertNotIn("filter.glob.clean", keys)

    def test_a_filter_the_local_config_includes_is_turned_off(self):
        clean, ran = self.filter_script("included")
        included = self.base / "included.cfg"
        included.write_text(f'[filter "inc"]\n\tclean = {clean}\n', encoding="utf-8")
        self.commit({"a.py": "a\n"}, "*.py filter=inc\n")
        git(self.root, "config", "include.path", str(included))
        with gitutil.system_only():
            self.assertEqual(gitutil.dirty(str(self.root)), ["a.py"])
            gitutil.hash_files(["a.py"], str(self.root))
        self.assertFalse(ran.exists())
        gitutil.hash_files(["a.py"], str(self.root))
        self.assertTrue(ran.exists(), "the setup is not real: the included filter never runs")

    def test_a_global_config_file_inside_the_repository_counts_as_the_repositorys(self):
        # A project setting that points HOME into the repository makes a file the agent can write the "global" config.
        clean, ran = self.filter_script("planted")
        fsmonitor = self.script("fsmonitor.sh", f"echo fsmonitor >> {ran}\nexit 1")
        self.commit({"a.py": "a\n"}, "*.py filter=planted\n")
        text = f'[filter "planted"]\n\tclean = {clean}\n[core]\n\tfsmonitor = {fsmonitor}\n'
        with mock.patch.dict(os.environ, self.global_config(text, home=self.root)):
            with gitutil.system_only():
                self.assertIn("a.py", gitutil.dirty(str(self.root)))
                gitutil.hash_files(["a.py"], str(self.root))
            self.assertFalse(ran.exists())
        # The test run names its own global config in GIT_CONFIG_GLOBAL, which system_only drops for HOME's.
        with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(self.root / ".gitconfig")}):
            gitutil.hash_files(["a.py"], str(self.root))
        self.assertTrue(ran.exists(), "the setup is not real: the planted filter never runs")

    def test_the_users_safe_directory_and_excludes_file_stay(self):
        (self.home / "ignore").write_text(".DS_Store\n", encoding="utf-8")
        (self.root / ".DS_Store").write_bytes(b"\0")
        text = f"[safe]\n\tdirectory = *\n[core]\n\texcludesFile = {self.home / 'ignore'}\n"
        # Only the user's config here: the machine's system config (a CI runner's sets safe.directory) is left out.
        env = {**self.global_config(text), "XDG_CONFIG_HOME": str(self.home / ".config")}
        system_env = gitutil._system_env
        no_system = mock.patch.object(gitutil, "_system_env", lambda *a, **k: {**system_env(*a, **k), "GIT_CONFIG_NOSYSTEM": "1"})
        with mock.patch.dict(os.environ, env), no_system:
            with gitutil.system_only():
                self.assertEqual(gitutil.run(["config", "--get-all", "safe.directory"], str(self.root)).strip(), "*")
                self.assertNotIn(".DS_Store", gitutil.dirty(str(self.root), untracked=True))
                self.assertNotIn(".DS_Store", gitutil.changed_since(str(self.root), "HEAD"))
                keys = dict(gitutil._system_overrides(gitutil.system_git(), str(self.root), {}))
        self.assertFalse([k for k in keys if k.startswith(("safe.", "core.excludesfile"))], keys)
        self.assertFalse(any(k.startswith("GIT_CONFIG_GLOBAL") or k == "GIT_CONFIG_NOSYSTEM" for k in gitutil._system_env("/usr/bin/git", None)))

    def test_a_crafted_key_name_cannot_inject_an_option(self):
        # A subsection may hold any byte but a newline or NUL: `=`, a space, a leading `-`. Through `-c key=` git would
        # split it on the `=`; through GIT_CONFIG_KEY_<n> it is taken whole.
        clean, ran = self.filter_script("crafted")
        self.commit({"a.py": "a\n"}, "*.py filter=-c=core.fsmonitor\n")
        for key in ("filter.-c=core.fsmonitor.clean", "filter.-x y=z.clean", "diff.--upload-pack=/tmp/x.textconv"):
            git(self.root, "config", key, str(clean))
        with gitutil.system_only():
            self.assertEqual(gitutil.dirty(str(self.root)), ["a.py"])
            gitutil.hash_files(["a.py"], str(self.root))
            keys = dict(gitutil._system_overrides(gitutil.system_git(), str(self.root), {}))
        self.assertFalse(ran.exists())
        gitutil.hash_files(["a.py"], str(self.root))
        self.assertTrue(ran.exists(), "the setup is not real: the crafted filter never runs")
        for key in ("filter.-c=core.fsmonitor.clean", "filter.-x y=z.clean", "diff.--upload-pack=/tmp/x.textconv"):
            self.assertEqual(keys.get(key), "", key)

    def test_a_key_that_does_not_parse_denies_in_an_aidd_repository(self):
        for good in ("filter.lfs.clean", "filter.-x y=z.clean", "diff.a.b.textconv", "core.fsmonitor"):
            self.assertTrue(gitutil._valid_key(good), good)
        for bad in ("filter", "filter..", ".x.clean", "fil ter.x.clean", "filter.x.cl=ean", "filter.x\ny.clean", "filter.x\0.clean", "filter.x.9clean"):
            self.assertFalse(gitutil._valid_key(bad), bad)
        event = json.dumps({"tool_name": "Edit", "cwd": str(self.root), "tool_input": {"file_path": str(self.root / "a.py")}})
        out = io.StringIO()
        with mock.patch.object(gitutil, "_valid_key", return_value=False):
            git(self.root, "config", "filter.x.clean", "/bin/cat")
            pre_tool.pre_tool_hook(io.StringIO(event), out)
        decision = json.loads(out.getvalue())["hookSpecificOutput"]
        self.assertEqual((decision["permissionDecision"], denial_log.reason_code(decision["permissionDecisionReason"])), ("deny", "guard_failed"))

    def test_a_config_probe_that_times_out_denies_with_a_reason(self):
        event = json.dumps({"tool_name": "Edit", "cwd": str(self.root), "tool_input": {"file_path": str(self.root / "a.py")}})
        out = io.StringIO()
        with mock.patch.object(gitutil, "_CONFIG_TIMEOUT_SECONDS", 1e-6):
            pre_tool.pre_tool_hook(io.StringIO(event), out)
        decision = json.loads(out.getvalue())["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("timed out", decision["permissionDecisionReason"])

    def test_the_probes_fit_the_hooks_20_seconds(self):
        # A `--version` check gets 4 s, then one retry of 10 s on a cold machine, within 14 s for every candidate; the
        # config read gets 4 s. That leaves 2 s of the hook's 20 s for the guard's own git calls.
        self.assertEqual((gitutil._VERSION_TIMEOUTS_SECONDS, gitutil._VERSION_BUDGET, gitutil._CONFIG_TIMEOUT_SECONDS), ((4.0, 10.0), 14.0, 4.0))
        self.assertLessEqual(gitutil._VERSION_BUDGET + gitutil._CONFIG_TIMEOUT_SECONDS, 18.0)


@unittest.skipIf(os.name == "nt", "the fake git is a POSIX shell script")
class SlowGitTests(unittest.TestCase):
    """A cold machine can take seconds to start git the first time: one slow `--version` is retried once."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()

    def slow_git(self, name: str, seconds: float) -> str:
        path = self.base / name
        path.write_text(f"#!/bin/sh\nexec /bin/sleep {seconds}\n", encoding="utf-8")
        path.chmod(0o755)
        return str(path)

    def probes(self, git: str, timeouts: tuple[float, float]) -> tuple[str | None, list[float]]:
        """system_git() with `git` as the only candidate: what it chose, and the timeout of each `--version` try."""
        with mock.patch.object(gitutil, "SYSTEM_GITS", (git,)), mock.patch.object(gitutil, "_VERSION_TIMEOUTS_SECONDS", timeouts):
            with mock.patch.object(gitutil, "_run_probe", wraps=gitutil._run_probe) as run:
                chosen = gitutil.system_git()
        return chosen, [round(c.args[1], 1) for c in run.call_args_list if c.args[0][1:] == ["--version"]]

    def test_a_git_that_answers_within_the_retry_is_chosen(self):
        slow = self.slow_git("slow", 1.5)
        self.assertEqual(self.probes(slow, (0.5, 8.0)), (slow, [0.5, 8.0]))

    def test_a_git_slower_than_the_retry_is_not_chosen(self):
        slower = self.slow_git("slower", 5)
        self.assertEqual(self.probes(slower, (0.3, 0.6)), (None, [0.3, 0.6]))

    def test_every_candidate_shares_one_budget(self):
        gits = tuple(self.slow_git(f"git{i}", 3) for i in range(4))
        began = time.monotonic()
        with mock.patch.object(gitutil, "SYSTEM_GITS", gits), mock.patch.object(gitutil, "_VERSION_BUDGET", 0.6):
            self.assertIsNone(gitutil.system_git())
        self.assertLess(time.monotonic() - began, 2.0)
