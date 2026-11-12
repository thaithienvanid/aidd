"""C6: `aidd test` says what it is doing. The runner reports each command as it starts, and the checkout of the base before
its red runs, to a caller that asks (`progress`); a caller that does not ask hears nothing. A full run in a dirty tree says
in its note that the run exits 1, and the exit table says the same."""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import git, run_cli

from aidd.cli import arguments
from aidd.testing import runner as test_runner

PY = sys.executable.replace("\\", "/")
CONFIG = f"""aidd_version: "1.0.0"
profile: solo
owners:
  approvers: [bob]
tests:
  - name: unit
    command: ["{PY}", -c, print('suite ok')]
"""
SPEC = f"""---
type: spec
id: SPEC-1
title: Greeting says hello
change_type: feat
route: normal
confidence: high
open_questions: []
trace_id: spec-1
rollback: Revert the PR.
risk:
  summary: Adds a greeting function.
  dimensions: []
  irreversible: false
tasks:
  - id: T1
    title: Implement greet
    scope: [app/]
tests:
  files: [checks/test_greet.py]
  commands:
    - name: greet
      command: ["{PY}", checks/test_greet.py]
      new_behavior: true
---
## Context
Tiny example.
## Acceptance
Invariant: greet() returns "hello".
"""
TEST = "import sys\nsys.path.insert(0, '.')\nfrom app.greet import greet\nassert greet() == 'hello'\nprint('ok')\n"


def write(root: Path, rel: str, text: str) -> None:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text, encoding="utf-8")


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "a@example.com")
        git(self.root, "config", "user.name", "A")
        write(self.root, ".aidd/config.yaml", CONFIG)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "base")
        git(self.root, "checkout", "-qb", "feature")
        write(self.root, "specs/SPEC-1.md", SPEC)
        write(self.root, "checks/test_greet.py", TEST)
        write(self.root, "app/greet.py", "def greet():\n    return 'hello'\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec and code")
        self.out = str(self.root / ".aidd" / "evidence")

    def run_tests(self, **kwargs) -> tuple[dict, list[str], list[str]]:
        lines: list[str] = []
        ev, notes = test_runner.run_tests(repo=str(self.root), base="main", out_dir=self.out, progress=lines.append, **kwargs)
        return ev, notes, lines

    def test_each_command_says_it_starts_and_the_base_checkout_is_announced_before_the_red_runs(self):
        for in_place in (False, True):
            with self.subTest(in_place=in_place):
                ev, _, lines = self.run_tests(red_in_place=in_place)
                green = [r["name"] for r in ev["results"] if r["red_green"] == "green"]
                red = [r["name"] for r in ev["results"] if r["red_green"] == "red"]
                self.assertEqual(len(green), 2)
                self.assertEqual(len(red), 1)
                base = ev["base_sha"][:12]
                self.assertEqual(lines[: len(green)], [f"running {name} on head ({i} of {len(green)})" for i, name in enumerate(green, 1)])
                self.assertRegex(lines[len(green)], rf"^checking out base {base} ")
                self.assertEqual(lines[len(green) + 1 :], [f"running {name} on base ({i} of {len(red)})" for i, name in enumerate(red, 1)])

    def test_no_red_runs_announce_no_base_checkout(self):
        _, _, lines = self.run_tests(red=False)
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(line.startswith("running ") and " on head (" in line for line in lines), lines)

    def test_a_quick_check_announces_its_selected_commands_only(self):
        write(self.root, "app/greet.py", "def greet():\n    return 'hello'\n# edit\n")
        ev, _, lines = self.run_tests(changed=True)
        self.assertEqual(len(lines), len(ev["results"]))
        self.assertFalse(any("base" in line for line in lines), lines)

    def test_a_caller_that_does_not_ask_hears_nothing(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            test_runner.run_tests(repo=str(self.root), base="main", out_dir=self.out)
        self.assertEqual((out.getvalue(), err.getvalue()), ("", ""))


class DirtyTreeNoteTests(unittest.TestCase):
    """A full run in a dirty tree exits 1 whatever its results say, so its note says so; a run that excuses the tree does not."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "a@example.com")
        git(self.root, "config", "user.name", "A")
        write(self.root, ".aidd/config.yaml", CONFIG)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "base")
        git(self.root, "checkout", "-qb", "feature")
        write(self.root, "README.md", "# x\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "work")
        write(self.root, "untracked.txt", "x\n")  # makes the tree dirty
        self.out = str(self.root / ".aidd" / "evidence")

    def dirty_note(self, **kwargs) -> str | None:
        ev, notes = test_runner.run_tests(repo=str(self.root), base="main", out_dir=self.out, **kwargs)
        self.assertTrue(ev["dirty_tree"])
        return next((n for n in notes if n.startswith("dirty tree")), None)

    def test_a_full_run_says_it_exits_1_and_why(self):
        note = self.dirty_note()
        self.assertIn("exits 1", note or "")
        self.assertIn("untracked.txt", note or "")
        self.assertIn("commit or stash", note or "")

    def test_a_run_that_skips_red_does_not_claim_an_exit_it_does_not_make(self):
        note = self.dirty_note(red=False)
        self.assertIsNotNone(note)
        self.assertNotIn("exits 1", note or "")

    def test_the_exit_table_names_what_else_makes_a_test_run_exit_1(self):
        row = dict(arguments.EXIT_CODES)["`test`"]
        for cause in ("a test failed", "ran no command", "dirty tree"):
            self.assertIn(cause, row[1])


class LateLanguageBytecodeTests(unittest.TestCase):
    """Empty-repo `aidd init` followed by Python + unittest gives an actionable `aidd upgrade --yes` fix on dirty bytecode."""

    def test_dirty_bytecode_after_empty_init_names_aidd_upgrade_and_recovers(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.email", "t@example.com")
            git(root, "config", "user.name", "T")
            git(root, "config", "commit.gpgsign", "false")
            git(root, "commit", "-q", "--allow-empty", "-m", "empty")
            with contextlib.chdir(root):
                code, out = run_cli("init", "--profile", "solo", "--ci", "none")
                self.assertEqual(code, 0, out)
            git(root, "add", "-A")
            git(root, "commit", "-qm", "aidd init")

            write(root, "src/booking.py", "def ok():\n    return True\n")
            write(
                root,
                "tests/test_booking.py",
                "import unittest\nfrom src.booking import ok\nclass T(unittest.TestCase):\n    def test_ok(self): self.assertTrue(ok())\n",
            )
            git(root, "add", "src/booking.py", "tests/test_booking.py")
            git(root, "commit", "-qm", "add python")

            res = subprocess.run([sys.executable, "-m", "unittest", "tests/test_booking.py", "-q"], cwd=root, capture_output=True, text=True, check=False)
            self.assertEqual(res.returncode, 0, res.stderr)

            with contextlib.chdir(root):
                code, out = run_cli("test")
            self.assertEqual(code, 1, out)
            self.assertIn("aidd upgrade --yes", out)
            self.assertIn(".gitignore", out)
            self.assertNotIn("commit or stash", out)
            ev = json.loads((root / ".aidd" / "evidence" / "evidence.json").read_text(encoding="utf-8"))
            self.assertTrue(ev["dirty_tree"])

            # A real untracked file alongside bytecode keeps commit-or-stash advice.
            write(root, "notes.txt", "wip\n")
            with contextlib.chdir(root):
                code, mixed_out = run_cli("test")
            self.assertEqual(code, 1, mixed_out)
            self.assertIn("commit or stash", mixed_out)
            (root / "notes.txt").unlink()

            with contextlib.chdir(root):
                code, up_out = run_cli("upgrade", "--yes")
                self.assertEqual(code, 0, up_out)
            git(root, "add", ".gitignore")
            git(root, "commit", "-qm", "add python gitignore")
            with contextlib.chdir(root):
                code, clean_out = run_cli("test")
            self.assertEqual(code, 0, clean_out)


if __name__ == "__main__":
    unittest.main()
