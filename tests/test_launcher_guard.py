"""Only an installed aidd writes the user launcher, `~/.aidd/bin/aidd`, which every repository's MCP server and delegation
hook start through. A source checkout (a `src/` tree on PYTHONPATH, an editable install, any path that is no install)
leaves it as it is, and `aidd doctor` warns about a launcher that starts one, or one whose path is gone."""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import aidd_here, aidd_subprocess, git, hermetic_environ

from aidd.setup import adoption, doctor_probes, mcp_wiring

POSIX = os.name == "posix"
SENTINEL = '#!/bin/sh\n# another aidd\'s launcher, which a source run must not touch\nexec /usr/bin/true "$@"\n'


def loader_script(source: str, python: str | None = None) -> str:
    return mcp_wiring.launcher_script([python or sys.executable, "-I", "-c", mcp_wiring.LOADER, source, "aidd"])


@unittest.skipUnless(POSIX, "the user launcher is a POSIX script")
class SourceCheckoutLeavesTheLauncherTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.home = self.base / "home"
        self.launcher = self.home / ".aidd" / "bin" / "aidd"
        self.launcher.parent.mkdir(parents=True)
        self.launcher.write_text(SENTINEL, encoding="utf-8")
        patcher = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_source_run_keeps_the_launcher_byte_for_byte_and_says_so(self):
        actions: list[str] = []
        mcp_wiring.install_user_launcher(self.base / "repo", actions)  # these tests run from a source checkout
        self.assertEqual(self.launcher.read_text(encoding="utf-8"), SENTINEL)
        self.assertEqual(len(actions), 1)
        self.assertTrue(
            actions[0].startswith(
                "kept     ~/.aidd/bin/aidd (this aidd runs from a source checkout, so it stays as it is; install aidd with `uv tool install git+https://"
            ),
            actions,
        )

    def test_a_source_run_writes_none_where_there_is_none(self):
        self.launcher.unlink()
        actions: list[str] = []
        mcp_wiring.install_user_launcher(self.base / "repo", actions)
        self.assertFalse(self.launcher.exists())
        self.assertIn("so it writes none; install aidd with `uv tool install git+https://github.com/thaithienvanid/aidd`, then run `aidd init`", actions[0])

    def test_an_installed_run_writes_it(self):
        actions: list[str] = []
        with mock.patch.object(mcp_wiring, "_on_default_path", return_value=True):  # aidd in this interpreter's site-packages
            mcp_wiring.install_user_launcher(self.base / "repo", actions)
            argv = mcp_wiring.launcher()
        self.assertEqual(argv[1:], ["-I", "-m", "aidd"])
        self.assertEqual(self.launcher.read_text(encoding="utf-8"), mcp_wiring.launcher_script(argv))
        self.assertTrue(actions[0].startswith("wrote    ~/.aidd/bin/aidd"), actions)

    def test_an_installed_dry_run_lists_the_launcher_and_writes_nothing(self):
        repo = self.base / "repo"
        repo.mkdir()
        git(repo, "init", "-q")
        self.launcher.unlink()
        with mock.patch.object(mcp_wiring, "_on_default_path", return_value=True):  # aidd in this interpreter's site-packages
            done = aidd_here(
                "init", ".", "--dry-run", "--profile", "solo", "--ci", "none", "--harness", "claude-code", "--approvers", "email:a@example.com", cwd=repo
            )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertRegex(done.stdout, r"(?m)^would write ~/\.aidd/bin/aidd \(the aidd MCP server of every repository here starts ")
        self.assertFalse(self.launcher.exists(), "a dry run wrote the launcher")
        self.assertEqual([p for p in self.home.rglob("*") if p.is_file()], [])

    def test_the_real_command_from_a_source_checkout_leaves_the_launcher(self):
        repo = self.base / "repo"
        repo.mkdir()
        git(repo, "init", "-q")
        env = {**hermetic_environ(), "HOME": str(self.home), "XDG_CACHE_HOME": str(self.base / "cache"), "CLAUDE_CONFIG_DIR": str(self.base / "claude")}
        for command in (
            ("init", ".", "--profile", "solo", "--ci", "none", "--harness", "claude-code", "--approvers", "email:a@example.com"),
            ("upgrade", "--yes"),
        ):
            with self.subTest(command=command[0]):
                done = aidd_subprocess(*command, cwd=repo, env=env)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(self.launcher.read_bytes(), SENTINEL.encode())
                if command[0] == "init":
                    self.assertIn("kept     ~/.aidd/bin/aidd (this aidd runs from a source checkout", done.stdout)
                    self.assertTrue((repo / ".mcp.json").is_file(), "everything else init writes is unchanged")


@unittest.skipUnless(POSIX, "the user launcher is a POSIX script")
class WhatCountsAsInstalledTests(unittest.TestCase):
    def test_each_install_form_is_installed_and_a_source_tree_is_not(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d).resolve()
            pyz = base / "aidd.pyz"
            pyz.write_bytes(b"zip")
            plugin = base / "home" / "plugins" / "cache" / "aidd" / "aidd" / "1.0.0"
            (plugin / ".claude-plugin").mkdir(parents=True)
            (plugin / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
            (plugin / "src").mkdir()
            tree = base / "work" / "src"
            tree.mkdir(parents=True)
            python = sys.executable
            user_site = base / "user-site"
            user_site.mkdir()
            cases = {
                "the user's site-packages (pip install --user)": ([python, "-I", "-c", "x", str(user_site), "aidd"], True),
                "site-packages (uv, pipx, the installer)": ([python, "-I", "-m", "aidd"], True),
                "the zipapp": ([python, "-I", "-c", "x", str(pyz), "aidd"], True),
                "the plugin's own copy": ([python, "-I", "-c", "x", str(plugin / "src"), "aidd"], True),
                "a source tree": ([python, "-I", "-c", "x", str(tree), "aidd"], False),
                "a path that is gone": ([python, "-I", "-c", "x", str(base / "gone" / "src"), "aidd"], False),
            }
            with mock.patch("site.getusersitepackages", return_value=str(user_site)):
                for name, (argv, want) in cases.items():
                    with self.subTest(name):
                        self.assertEqual(mcp_wiring.installed(argv), want)


@unittest.skipUnless(POSIX, "the user launcher is a POSIX script")
class DoctorChecksTheLauncherTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.home = self.base / "home"
        self.launcher = self.home / ".aidd" / "bin" / "aidd"
        self.launcher.parent.mkdir(parents=True)
        patcher = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def checks(self, text: str | None) -> list[tuple[str, str]]:
        if text is not None:
            self.launcher.write_text(text, encoding="utf-8")
        return doctor_probes.launcher_checks()

    def test_a_launcher_that_starts_a_source_tree_warns_and_names_the_step(self):
        tree = self.base / "wt" / "src"
        tree.mkdir(parents=True)
        ((level, message),) = self.checks(loader_script(str(tree)))
        self.assertEqual(level, "warn")
        self.assertIn(str(tree), message)
        self.assertIn("then run `aidd init` to write it again", message)

    def test_a_launcher_whose_path_is_gone_warns(self):
        gone = self.base / "deleted-worktree" / "src"
        ((level, message),) = self.checks(loader_script(str(gone)))
        self.assertEqual(level, "warn")
        self.assertIn(f"{gone}, which no longer exists", message)
        ((level, message),) = self.checks(loader_script(str(self.base), python=str(self.base / "no-python")))
        self.assertIn("no-python, which no longer exists", message)

    def test_a_python_named_without_a_path_is_found_on_path_before_it_is_called_gone(self):
        tree = self.base / "wt" / "src"
        tree.mkdir(parents=True)
        pyz = self.base / "aidd.pyz"
        pyz.write_bytes(b"zip")
        self.assertEqual(self.checks(loader_script(str(pyz), python="python3")), [])
        ((level, message),) = self.checks(loader_script(str(pyz), python="no-such-python-anywhere"))
        self.assertIn("no-such-python-anywhere, which no longer exists", message)
        self.assertIn("uv tool install git+https://github.com/thaithienvanid/aidd", message)

    def test_an_install_a_missing_launcher_and_a_launcher_of_the_persons_own_are_quiet(self):
        self.assertEqual(self.checks(mcp_wiring.launcher_script([sys.executable, "-I", "-m", "aidd"])), [])
        pyz = self.base / "aidd.pyz"
        pyz.write_bytes(b"zip")
        self.assertEqual(self.checks(loader_script(str(pyz))), [])
        self.assertEqual(self.checks(SENTINEL), [])
        self.assertEqual(self.checks("not a script at all\n"), [])
        self.launcher.unlink()
        self.assertEqual(doctor_probes.launcher_checks(), [])

    def test_aidd_doctor_carries_the_warning(self):
        repo = self.base / "repo"
        repo.mkdir()
        git(repo, "init", "-q")
        adoption.init(repo, adoption.InitOptions(profile="solo", ci="none", links=[], approvers=["email:a@example.com"], harnesses=["claude-code"]))
        from aidd.setup import doctor_checks

        tree = self.base / "wt" / "src"
        tree.mkdir(parents=True)
        self.launcher.write_text(loader_script(str(tree)), encoding="utf-8")
        lines = [m for lvl, m in doctor_checks.doctor(repo) if lvl == "warn" and "~/.aidd/bin/aidd starts" in m]
        self.assertEqual(len(lines), 1, lines)
        shutil.rmtree(tree)
        lines = [m for lvl, m in doctor_checks.doctor(repo) if lvl == "warn" and "~/.aidd/bin/aidd starts" in m]
        self.assertTrue(lines and "no longer exists" in lines[0], lines)


if __name__ == "__main__":
    unittest.main()
