"""Where a `shared_reads` scope starts, where it ends, and what drops what it kept.

Invariant: a scope lasts for the work of one command, and a read kept in it is never returned after a write that could change
its answer: not after a git call aidd makes (`test_git_read_forms`), not after a program aidd starts, and not in another
environment, because git reads its config by the environment.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers

from aidd.delegation import outcome
from aidd.delegation.check import Request
from aidd.kernel import git as kernel_git
from aidd.kernel import git_reads
from aidd.kernel import resources
from aidd.setup import adoption, claude_plugins, pins, uninstalling, upgrading
from aidd.testing import runner as test_runner


def repo(root: Path) -> str:
    """A repository on `feat` with a commit; `main` exists too."""
    root.mkdir(parents=True)
    helpers.git(root, "init", "-q", "-b", "main")
    helpers.git(root, "commit", "-q", "--allow-empty", "-m", "base")
    helpers.git(root, "switch", "-qc", "feat")
    return str(root.resolve())


class AKeptReadIsAnswerOnlyInTheEnvironmentThatAsked(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = repo(Path(self.tmp.name) / "repo")
        for name, value in (("one", "first"), ("two", "second")):
            Path(self.tmp.name, f"{name}.gitconfig").write_text(f"[user]\n\tname = {value}\n", encoding="utf-8")

    def global_config(self, name: str):
        return mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(Path(self.tmp.name) / f"{name}.gitconfig")})

    def test_a_setting_read_in_one_environment_is_read_again_in_another(self):
        """The global config file is chosen by the environment, so the same read in the same folder differs between two."""
        ask = ["config", "--get", "user.name"]
        with git_reads.shared_reads():
            with self.global_config("one"):
                self.assertEqual(kernel_git.run(ask, self.root, check=False).strip(), "first")
            with self.global_config("two"):
                self.assertEqual(kernel_git.run(ask, self.root, check=False).strip(), "second")
            with self.global_config("one"):
                self.assertEqual(kernel_git.run(ask, self.root, check=False).strip(), "first")

    def test_the_same_environment_asks_git_once(self):
        """The control: the key still shares an answer where nothing changed."""
        started: list[str] = []
        real = subprocess.run

        def counted(argv, *args, **kwargs):
            started.append(argv[0])
            return real(argv, *args, **kwargs)

        with self.global_config("one"), mock.patch.object(kernel_git.subprocess, "run", counted), git_reads.shared_reads():
            for _ in range(3):
                kernel_git.run(["config", "--get", "user.name"], self.root, check=False)
        self.assertEqual(started, ["git"])

    def test_the_filters_a_config_names_are_read_again_when_the_environment_changes(self):
        """The blanks a call gets come from the config git reads, and `GIT_CONFIG_COUNT` adds a setting to it."""
        named = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "filter.evil.clean", "GIT_CONFIG_VALUE_0": "touch x"}
        with git_reads.shared_reads():
            self.assertNotIn("filter.evil.clean", dict(kernel_git._config_pairs(["status"], self.root, remote=False)))
            with mock.patch.dict(os.environ, named):
                self.assertIn("filter.evil.clean", dict(kernel_git._config_pairs(["status"], self.root, remote=False)))


class AProgramAiddStartsDropsWhatWasKept(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = repo(Path(self.tmp.name) / "repo")

    def test_a_test_command_that_switches_the_branch_is_seen_by_the_next_read(self):
        with git_reads.shared_reads():
            self.assertEqual(kernel_git.current_branch(self.root), "feat")
            test_runner.run_test_command(["git", "switch", "-q", "main"], cwd=self.root, log=Path(self.tmp.name) / "log", timeout_seconds=60)
            self.assertEqual(kernel_git.current_branch(self.root), "main")

    def test_a_test_command_whose_cleanup_fails_still_drops_what_was_kept(self):
        with git_reads.shared_reads():
            self.assertEqual(kernel_git.current_branch(self.root), "feat")
            with mock.patch.object(test_runner.processes, "kill_group", side_effect=RuntimeError("the cleanup failed")), self.assertRaises(RuntimeError):
                test_runner.run_test_command(["git", "switch", "-q", "main"], cwd=self.root, log=Path(self.tmp.name) / "log", timeout_seconds=60)
            self.assertEqual(kernel_git.current_branch(self.root), "main")

    def test_a_plugin_install_that_switches_the_branch_is_seen_by_the_next_read(self):
        for ends in ("returns", "times out"):
            with self.subTest(install=ends):
                self.install_that_switches_the_branch(ends)

    def install_that_switches_the_branch(self, ends: str):
        subprocess.run(["git", "switch", "-q", "feat"], cwd=self.root, check=True, capture_output=True)

        def installer(cmd, **kwargs):
            subprocess.run(["git", "switch", "-q", "main"], cwd=self.root, check=True, capture_output=True)
            if ends == "times out":
                raise subprocess.TimeoutExpired(cmd, 300)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        which = lambda name, path=None: "/usr/bin/claude" if name == "claude" else shutil.which(name, path=path)  # noqa: E731
        with (
            mock.patch.dict(os.environ, {"AIDD_OFFLINE": "0"}),
            mock.patch.object(shutil, "which", which),
            mock.patch.object(pins, "remote_refs", lambda *args, **kwargs: None),  # the release lookup would drop the reads itself
            mock.patch.object(claude_plugins, "PLUGIN_RUNNER", installer),
            git_reads.shared_reads(),
        ):
            self.assertEqual(kernel_git.current_branch(self.root), "feat")
            claude_plugins.install_claude_plugins(Path(self.root), [], aidd_team=False)
            self.assertEqual(kernel_git.current_branch(self.root), "main")

    def test_every_program_the_product_starts_forgets_the_reads_or_writes_no_repository(self):
        """Each place that starts a program (not git) is named here, with why its repository is safe or that it drops the reads."""
        starts = {
            "src/aidd/delegation/platform.py": "writes no repository: `gh api` reads the platform",
            "src/aidd/evals/suites.py": "aidd eval runs by hand, in no scope, in a clone it made",
            "src/aidd/setup/claude_plugins.py": "forgets",
            "src/aidd/setup/doctor_probes.py": "writes no repository: a tool's `--version`",
            "src/aidd/setup/self_updating.py": "aidd self-update runs in no scope, in aidd's own checkout",
            "src/aidd/testing/runner.py": "forgets",
        }
        found = set()
        for path in sorted((helpers.ROOT / "src" / "aidd").rglob("*.py")):
            rel = str(path.relative_to(helpers.ROOT))
            if rel == "src/aidd/kernel/git.py":
                continue
            text = path.read_text(encoding="utf-8")
            for node in ast.walk(ast.parse(text)):
                used = node.func if isinstance(node, ast.Call) else node.value if isinstance(node, ast.Assign) else None  # a call, or `X = subprocess.run`
                launches = isinstance(used, ast.Attribute) and isinstance(used.value, ast.Name) and used.value.id == "subprocess"
                if launches and used.attr in ("run", "Popen", "call", "check_call", "check_output"):  # type: ignore[union-attr]
                    found.add(rel)
            if starts.get(rel) == "forgets":
                self.assertIn("git_reads.forget_reads()", text, f"{rel} starts a program that may write a repository")
        for rel in found - starts.keys():
            self.fail(f"{rel} starts a program: name it here, and drop the kept reads after it if it may write a repository")
        for rel in starts.keys() - found:
            self.fail(f"{rel} starts no program any more: drop it from the list")


def in_generator(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    """Whether the nearest function around `node` yields (its own body, not a function nested in it)."""
    function = parents.get(node)
    while function is not None and not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
        function = parents.get(function)
    if function is None:
        return False
    pending = list(function.body)
    while pending:
        current = pending.pop()
        if isinstance(current, (ast.Yield, ast.YieldFrom)):
            return True
        if not isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            pending.extend(ast.iter_child_nodes(current))
    return False


SCOPE_OPENERS = ("shared_reads", "rendered_once")


def scope_problems(tree: ast.Module) -> tuple[int, list[str]]:
    """How many scope openers `tree` calls, and what is wrong with each. A scope is the context of a `with`, or a decorator of
    one plain function (a decorator is a `with` around each call, so it ends where the function returns), and nothing holds
    one open. An opener in a generator, or a decorator of a generator or an async function, ends before the work is done."""
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    problems, calls = [], 0
    for node in ast.walk(tree):
        name = node.func.attr if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) else getattr(getattr(node, "func", None), "id", "")
        if isinstance(node, ast.Call) and name in SCOPE_OPENERS:
            calls += 1
            parent = parents[node]
            opens = isinstance(parent, ast.withitem) or (isinstance(parent, ast.FunctionDef) and node in parent.decorator_list)
            if not opens:
                problems.append(f"{node.lineno}: a scope opened where nothing ends it")
            elif in_generator(node, parents):
                problems.append(f"{node.lineno}: a scope opened in a generator stays open in the code that iterates it")
        if isinstance(node, ast.Attribute) and node.attr in ("enter_context", "__enter__"):
            problems.append(f"{node.lineno}: code that holds a context open can outlive its command")
    return calls, problems


class NoScopeIsOpenedWithoutItsEnd(unittest.TestCase):
    def test_a_scope_is_opened_only_by_a_with_statement_or_the_decorator(self):
        """`shared_reads()` and `rendered_once()` in the product are each the context of a `with` or a decorator of one function,
        so the scope ends where its block or function does, and no code holds one open through `enter_context` or `__enter__`."""
        calls = 0
        for path in sorted((helpers.ROOT / "src" / "aidd").rglob("*.py")):
            found, problems = scope_problems(ast.parse(path.read_text(encoding="utf-8")))
            calls += found
            with self.subTest(file=path.name):
                self.assertEqual(problems, [])
        self.assertGreaterEqual(calls, 8, "the control: the scan finds the product's scopes, the decorators among them")

    def test_the_scan_sees_each_way_a_scope_is_opened_and_each_way_it_outlives_its_work(self):
        cases = [
            ("a with", "def f():\n    with git_reads.shared_reads():\n        pass\n", 0),
            ("a decorator of a function", "@git_reads.shared_reads()\ndef f():\n    return 1\n", 0),
            ("a decorator under another", "@git_reads.shared_reads()\n@team_install.rendered_once()\ndef f():\n    return 1\n", 0),
            ("a decorator of a generator", "@git_reads.shared_reads()\ndef f():\n    yield 1\n", 1),
            ("a decorator of an async function", "@git_reads.shared_reads()\nasync def f():\n    return 1\n", 1),
            ("a with in a generator", "def f():\n    with git_reads.shared_reads():\n        yield 1\n", 1),
            ("a call that nothing ends", "def f():\n    scope = git_reads.shared_reads()\n", 1),
            ("an open held by a stack", "def f(stack):\n    stack.enter_context(git_reads.shared_reads())\n", 2),
        ]
        for name, source, expected in cases:
            with self.subTest(name):
                _, problems = scope_problems(ast.parse(source))
                self.assertEqual(len(problems), expected, problems)


class EachScopeNameHasOneHome(unittest.TestCase):
    """`git_reads` defines the names of the scope, and no module re-exports one. A test may patch `forget_reads` or `current` there,
    because every caller looks them up as it runs. It may not patch `shared_reads`: `init`, `upgrade`, `uninstall`, and the delegate
    check apply it as a decorator, which binds when their module loads, so a patch made later misses them (`test_patch_targets.py`
    fails a patch of a name that a module applies as a decorator)."""

    NAMES = ("forget_reads", "shared_reads", "in_shared_reads")
    DOORS = {"git", "kernel_git", "gitutil"}

    def test_git_re_exports_no_name_of_the_scope_and_no_separate_decorator_exists(self):
        for name in self.NAMES:
            with self.subTest(name):
                self.assertFalse(hasattr(kernel_git, name), "a name with a second home has no patch target a test may use")
        self.assertFalse(hasattr(git_reads, "in_shared_reads"), "the scope is its own decorator")
        self.assertIsNone(importlib.util.find_spec("aidd.kernel.scopes"), "a second way to decorate")

    def test_no_code_reaches_a_name_of_the_scope_through_git(self):
        for root in (helpers.ROOT / "src" / "aidd", helpers.ROOT / "tests"):
            for path in sorted(root.rglob("*.py")):
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                    if isinstance(node, ast.Attribute) and node.attr in self.NAMES and isinstance(node.value, ast.Name) and node.value.id in self.DOORS:
                        self.fail(f"{path.relative_to(helpers.ROOT)}:{node.lineno} reaches {node.attr} through {node.value.id}")


class ACommandRunsInOneScopeAndEndsIt(unittest.TestCase):
    def watch(self, module, name: str) -> list[bool]:
        """Patch `module.name` to note whether a scope is open when it runs, and to run as before."""
        seen: list[bool] = []
        real = getattr(module, name)

        def spy(*args, **kwargs):
            seen.append(git_reads.current() is not None)
            return real(*args, **kwargs)

        patch = mock.patch.object(module, name, spy)
        patch.start()
        self.addCleanup(patch.stop)
        return seen

    def test_init_upgrade_uninstall_and_the_delegate_check_each_run_inside_one_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            fresh = repo(Path(tmp) / "fresh")
            adopted = str(helpers.make_repo(Path(tmp) / "adopted"))
            inits = self.watch(adoption, "planned_config")
            adoption.init(Path(fresh), adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=[], approvers=["@x"], skill=False))
            upgrades = self.watch(upgrading, "older_than_repository")
            upgrading.upgrade(Path(adopted))
            removals = self.watch(resources, "data_dir")
            uninstalling.uninstall(Path(adopted))
            checks: list[bool] = []

            def stop(request):
                checks.append(git_reads.current() is not None)
                raise RuntimeError("the check's own work is not what this tests")

            with mock.patch.object(outcome, "evaluate", stop), self.assertRaises(RuntimeError):
                outcome.run_check(Request(action="git.push", cwd=adopted))
        for command, seen in {"init": inits, "upgrade": upgrades, "uninstall": removals, "check": checks}.items():
            with self.subTest(command=command):
                self.assertTrue(seen and all(seen), "the command's work ran with no scope open")
        self.assertIsNone(git_reads.current(), "a scope outlived its command")

    def test_status_validate_risk_and_init_each_run_inside_one_scope(self):
        """The commands a person and an agent run most read the repository and write nothing, so every git call of each runs in a scope."""
        with tempfile.TemporaryDirectory() as tmp:
            adopted = str(helpers.make_repo(Path(tmp) / "adopted"))
            for argv in (("status",), ("validate",), ("risk", "--paths", "src/a.py"), ("init", "--dry-run", "--profile", "team")):
                with self.subTest(command=" ".join(argv)):
                    seen = self.watch(kernel_git, "_git")
                    self.assertEqual(helpers.aidd_here(*argv, cwd=adopted).returncode, 0, argv)
                    self.assertTrue(seen and all(seen), "a git call of the command ran with no scope open")
                    self.assertIsNone(git_reads.current(), "a scope outlived its command")

    def test_the_test_run_reads_inside_one_scope_and_a_test_command_ends_what_it_kept(self):
        """`aidd test` reads the head, the base, and the Specs from git; its commands may write the repository, so each one drops the reads."""
        with tempfile.TemporaryDirectory() as tmp:
            adopted = str(helpers.make_repo(Path(tmp) / "adopted"))
            helpers.git(adopted, "switch", "-qc", "change")
            config_file = Path(adopted, ".aidd", "config.yaml")
            config_file.write_text(
                config_file.read_text(encoding="utf-8") + 'tests:\n  - name: unit\n    command: ["python3", "-c", "raise SystemExit(0)"]\n', encoding="utf-8"
            )
            Path(adopted, "app.py").write_text("x = 1\n", encoding="utf-8")
            helpers.git(adopted, "add", "-A")
            helpers.git(adopted, "commit", "-qm", "a change")
            seen = self.watch(kernel_git, "_git")
            forgot: list[bool] = []
            real = git_reads.forget_reads

            def forgets():
                forgot.append(git_reads.current() is not None)
                real()

            with mock.patch.object(git_reads, "forget_reads", forgets):
                evidence, _ = test_runner.run_tests(repo=adopted, base="main", out_dir=str(Path(tmp) / "evidence"))
            self.assertTrue(evidence["results"], "the control: a command ran")
            self.assertTrue(seen and all(seen), "a git call of the run happened with no scope open")
            self.assertTrue(forgot and all(forgot), "a test command ended with no scope open to drop")
            self.assertIsNone(git_reads.current(), "a scope outlived its command")


if __name__ == "__main__":
    unittest.main()
