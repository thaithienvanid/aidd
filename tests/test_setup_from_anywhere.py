"""The setup commands (`init`, `upgrade`, `uninstall`, `doctor`) work on the repository's top, wherever a person starts them. For
every start folder and every way of naming the folder, the config lands at the top, or the command refuses and says where
the top is. It never writes a second aidd in a subfolder, and `init` never writes into a folder that no repository holds."""

import tempfile
import unittest
from pathlib import Path

from helpers import aidd_here, git

COMMANDS = ("init", "upgrade", "uninstall", "doctor")


class SetupFromAnywhere(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.top = Path(tmp.name).resolve() / "repo"
        (self.top / "sub" / "deeper").mkdir(parents=True)
        git(self.top, "init", "-q", "-b", "main")
        self.plain = Path(tmp.name).resolve() / "plain"
        self.plain.mkdir()

    def test_a_folder_inside_a_repository_is_refused_with_the_top_named(self):
        """Table: every command, started in a folder below the top, with the path `.` or a folder's name."""
        for command in COMMANDS:
            for start, path in (("sub", ["."]), ("sub/deeper", ["."]), (".", ["sub"])):
                with self.subTest(command=command, start=start, path=path):
                    here = self.top / start
                    run = aidd_here(command, *path, *(["--dry-run"] if command == "init" else []), cwd=here)
                    self.assertEqual(run.returncode, 2, run.stdout)
                    self.assertIn(f"`aidd {command} {self.top}`", run.stderr)
                    self.assertFalse((self.top / "sub" / ".aidd").exists())

    def test_with_no_path_init_works_on_the_top_from_any_folder_below(self):
        for start in ("sub", "sub/deeper"):
            with self.subTest(start=start):
                run = aidd_here("init", "--ci", "none", "--no-skill", cwd=self.top / start)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertTrue((self.top / ".aidd" / "config.yaml").is_file())
                self.assertEqual(sorted(p.name for p in (self.top / start).iterdir()), ["deeper"] if start == "sub" else [])
                for command in ("doctor", "upgrade", "uninstall"):
                    ran = aidd_here(command, cwd=self.top / start)
                    self.assertNotIn("not at its top", ran.stderr)
                    self.assertNotIn("no .aidd/config.yaml", ran.stdout, command)

    def test_the_top_named_by_a_path_is_accepted_from_anywhere(self):
        for path in (str(self.top), str(self.top / "sub" / ".."), str(self.top / ".")):
            with self.subTest(path=path):
                run = aidd_here("init", path, "--dry-run", cwd=self.top / "sub")
                self.assertEqual(run.returncode, 0, run.stderr)

    def test_init_in_a_folder_no_repository_holds_writes_nothing(self):
        """A real run refuses; a dry run says so and writes nothing; the folder stays empty either way."""
        real = aidd_here("init", cwd=self.plain)
        self.assertEqual(real.returncode, 2)
        self.assertIn("`git init`", real.stderr)
        dry = aidd_here("init", "--dry-run", cwd=self.plain)
        self.assertEqual(dry.returncode, 0)
        self.assertIn("`git init`", dry.stderr)
        self.assertEqual(list(self.plain.iterdir()), [])

    def test_upgrade_and_uninstall_in_a_folder_no_repository_holds_refuse_and_write_nothing(self):
        for command in ("upgrade", "uninstall"):
            for extra in ([], ["--yes"]):
                with self.subTest(command=command, extra=extra):
                    run = aidd_here(command, *extra, cwd=self.plain)
                    self.assertEqual(run.returncode, 2, run.stdout)
                    self.assertIn("`git init`", run.stderr)
                    self.assertEqual(list(self.plain.iterdir()), [])

    def test_a_folder_that_is_not_there_is_named(self):
        for command in ("upgrade", "uninstall", "doctor"):
            with self.subTest(command=command):
                run = aidd_here(command, "nothere", cwd=self.top)
                self.assertEqual(run.returncode, 2)
                self.assertIn("is not a directory", run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
