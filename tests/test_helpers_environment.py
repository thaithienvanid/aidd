"""The test environment is the same on every machine: the time zone, the language, the hash seed, and the user folders are
pinned for this process and every child, and what the helpers patch for the whole process is undone at exit."""

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import helpers

CHILD = (
    "import os, time, helpers\n"
    "from aidd.setup import adoption\n"
    "before = adoption.installed_harnesses is not helpers.real_installed_harnesses\n"
    "helpers._stop_global_patches()\n"
    "after = adoption.installed_harnesses is helpers.real_installed_harnesses\n"
    "print(before, after, os.environ['TZ'], os.environ['LC_ALL'], os.environ['PYTHONHASHSEED'], time.strftime('%Z'))\n"
)


class PinnedEnvironmentTests(unittest.TestCase):
    def test_the_clock_the_language_and_the_hash_seed_are_pinned(self):
        self.assertEqual((os.environ["TZ"], os.environ["LC_ALL"], os.environ["PYTHONHASHSEED"]), ("UTC", "C.UTF-8", "0"))
        if hasattr(time, "tzset"):
            self.assertEqual(time.strftime("%Z"), "UTC")

    def test_every_agents_session_variable_is_stripped(self):
        """`aidd init` wires the agent whose variable is set, so a suite run inside any agent must not see one."""
        from aidd.config import harnesses

        for var in harnesses.SESSION_ENV:
            with self.subTest(var=var):
                self.assertNotIn(var, os.environ)
                self.assertNotIn(var, helpers.hermetic_environ({var: "1"}))

    def test_the_user_folders_are_temporary_ones(self):
        sandbox = helpers._SANDBOX
        for name in ("XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
            with self.subTest(name=name):
                self.assertTrue(Path(os.environ[name]).is_relative_to(sandbox), os.environ[name])
        self.assertTrue(Path(os.environ["HOME"]).is_relative_to(sandbox))

    def test_a_python_a_test_starts_sees_the_same_values_and_the_global_patch_stops_at_exit(self):
        env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(Path(helpers.__file__).parent), str(helpers.ROOT / "src")])}
        done = subprocess.run(
            [sys.executable, "-c", CHILD], env=env, capture_output=True, text=True, timeout=helpers.SUBPROCESS_TIMEOUT, check=False, cwd=helpers.ROOT
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.split(), ["True", "True", "UTC", "C.UTF-8", "0", "UTC"], done.stderr)

    def test_the_axe_test_reads_the_copy_a_person_names_before_the_strip(self):
        """The helpers remove every AIDD_ variable, so the axe test's AIDD_AXE_JS is read first, or its advice never works."""
        tests = Path(helpers.__file__).parent
        env = {**os.environ, "AIDD_AXE_JS": "/elsewhere/axe.min.js", "PYTHONPATH": os.pathsep.join([str(tests), str(helpers.ROOT / "src")])}
        done = subprocess.run(
            [sys.executable, "-c", "import test_work_page_axe as t; print(t.AXE)"],
            env=env,
            capture_output=True,
            text=True,
            timeout=helpers.SUBPROCESS_TIMEOUT,
            check=False,
            cwd=tests,
        )
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "/elsewhere/axe.min.js"), done.stderr)


@unittest.skipUnless(os.name == "posix", "a fake program is a shell script")
class FakeProgramTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_a_fake_runs_its_own_text_by_any_name_the_shell_reached_it_with_and_whatever_PATH_holds(self):
        """The shim sources `<path>.body`. A bare `$0` (the shell was handed `gh`, not `./gh`) would make `.` search PATH, so a
        `gh.body` in a PATH folder would run instead."""
        fake = helpers.write_executable(self.dir / "gh", "#!/bin/sh\necho mine\n")
        decoy = self.dir / "decoy"
        decoy.mkdir()
        (decoy / "gh.body").write_text("echo decoy\n", encoding="utf-8")
        env = {"PATH": f"{decoy}{os.pathsep}/usr/bin{os.pathsep}/bin"}
        for argv in (["./gh"], ["sh", "gh"], [str(fake)]):
            with self.subTest(argv=argv):
                done = subprocess.run(argv, cwd=self.dir, env=env, capture_output=True, text=True, timeout=helpers.SUBPROCESS_TIMEOUT, check=False)
                self.assertEqual((done.returncode, done.stdout.strip()), (0, "mine"), done.stderr)

    def test_shell_fakes_are_one_file_so_only_their_text_tells_them_apart(self):
        """An edit in place, or an identity check (`os.path.samefile`, `test -ef`), sees every shell fake as the same file."""
        a = helpers.write_executable(self.dir / "a", "#!/bin/sh\necho a\n")
        b = helpers.write_executable(self.dir / "b", "#!/bin/sh\necho b\n")
        self.assertTrue(os.path.samefile(a, b))
        outputs = [subprocess.run([str(p)], capture_output=True, text=True, timeout=helpers.SUBPROCESS_TIMEOUT, check=False).stdout.strip() for p in (a, b)]
        self.assertEqual(outputs, ["a", "b"])


if __name__ == "__main__":
    unittest.main()
