"""`aidd upgrade --yes` ends by running the checks of `aidd validate`: it lists each error that remains, and exits 1."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from helpers import git

from aidd import config
from aidd.cli import app
from aidd.setup import upgrading

BAD = "---\ntype: proposal\nid: P-1\n---\n\nbody\n"  # a proposal without its required fields


def run_cli(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = app.main(list(argv))
    return code, out.getvalue()


class UpgradeValidateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "-c", "user.name=Maya", "-c", "user.email=maya@users.noreply.github.com", "commit", "-q", "--allow-empty", "-m", "start")
        (self.root / ".aidd").mkdir()
        (self.root / config.CONFIG_PATH).write_text('aidd_version: "1.0.0"\nprofile: solo\n', encoding="utf-8")
        (self.root / "proposals").mkdir()
        self.item = self.root / "proposals" / "P-1.md"

    def test_an_error_that_remains_is_listed_with_the_file_and_the_exit_is_1(self):
        self.item.write_text(BAD, encoding="utf-8")
        problems = [x for x in upgrading.upgrade(self.root, ref="v1.0.0", yes=True) if x.startswith(upgrading.UPGRADE_PROBLEM)]
        self.assertTrue(any("proposals/P-1.md" in x and "missing required field" in x for x in problems), problems)
        code, out = run_cli("upgrade", str(self.root), "--yes", "--ref", "v1.0.0")
        self.assertEqual(code, 1)
        self.assertRegex(out, r"\d+ problem\(s\) remain")

    def test_a_dry_run_and_a_clean_repository_report_no_problem(self):
        self.item.write_text(BAD, encoding="utf-8")
        self.assertEqual([x for x in upgrading.upgrade(self.root, ref="v1.0.0") if x.startswith(upgrading.UPGRADE_PROBLEM)], [])
        self.item.unlink()
        code, out = run_cli("upgrade", str(self.root), "--yes", "--ref", "v1.0.0")
        self.assertNotIn(upgrading.UPGRADE_PROBLEM, out)
        self.assertEqual(code, 0, out)

    def test_a_file_name_with_control_characters_prints_as_one_safe_line(self):
        (self.root / "proposals" / "P-2\x1b]0;X\x07.md").write_text(BAD.replace("P-1", "P-2"), encoding="utf-8")
        code, out = run_cli("upgrade", str(self.root), "--yes", "--ref", "v1.0.0")
        self.assertEqual(code, 1)
        self.assertIn("proposals/P-2", out)
        self.assertNotIn("\x1b", out)
        self.assertNotIn("\x07", out)


if __name__ == "__main__":
    unittest.main()
