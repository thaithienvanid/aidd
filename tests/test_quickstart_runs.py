"""The "Your first change" walk in docs/GUIDE.md runs as written: the practice repository, `aidd init` and `aidd doctor`,
the route of the first edit, and the tests of a minor change, in a temporary folder with `aidd` resolving to this checkout.

The agent's own steps (writing the Spec, the code, and the asks) are not commands, so the test does the agent's part by
hand where a command needs it: it writes the file the page names, on a branch, and runs the commands the page names.
Nothing here needs the network, a platform, or a real coding agent.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, src_pythonpath, write_executable

GUIDE = ROOT / "docs" / "GUIDE.md"
COMMAND_SECONDS = 300
BLOCK = re.compile(r"^```(\w*)\n(.*?)^```[ \t]*$", re.S | re.M)


def first_change(text: str) -> str:
    """The body of the guide's `## Your first change` section."""
    return text.split("\n## Your first change\n", 1)[1].split("\n## ", 1)[0]


def step(section: str, number: int) -> str:
    """The text of numbered step `number`, from its bold lead to the next step's."""
    m = re.search(rf"^\*\*{number}\. .*?(?=^\*\*\d+\. |\Z)", section, re.S | re.M)
    assert m, f"the guide's first change has no step {number}"
    return m.group(0)


def blocks(text: str, lang: str) -> list[str]:
    return [body for block_lang, body in BLOCK.findall(text) if block_lang == lang]


@unittest.skipIf(os.name == "nt", "the page's commands are sh")
@unittest.skipUnless(shutil.which("git") and shutil.which("sh"), "git and sh are required")
class FirstChangeRunsTests(unittest.TestCase):
    def setUp(self):
        self.section = first_change(GUIDE.read_text(encoding="utf-8"))
        tmp = tempfile.TemporaryDirectory(prefix="aidd-first-change-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        launcher = bin_dir / "aidd"
        write_executable(launcher, f'#!/bin/sh\nexec "{sys.executable}" -m aidd "$@"\n')
        self.home = self.tmp / "work"
        self.home.mkdir()
        self.env = {
            **os.environ,
            "PYTHONPATH": src_pythonpath(),  # with the read record when the run keeps one
            "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "AIDD_OFFLINE": "1",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        }

    def sh(self, script: str, expect: int = 0) -> str:
        done = subprocess.run(["sh", "-ec", script], cwd=self.home, env=self.env, capture_output=True, text=True, timeout=COMMAND_SECONDS)
        self.assertEqual(done.returncode, expect, f"{script}\n{done.stdout}\n{done.stderr}")
        return done.stdout + done.stderr

    def test_the_walk_takes_a_minor_change_to_green(self):
        self.sh(blocks(step(self.section, 1), "sh")[0])
        self.home = self.home / "aidd-practice"  # the page's first command ends with `cd aidd-practice`
        self.sh("\n".join(blocks(step(self.section, 2), "sh")))
        # The page names the suite with `--test`, so the config binds it in place of the smoke test.
        tests = re.search(r"(?ms)^tests:.*?(?=\n\n#|\Z)", (self.home / ".aidd" / "config.yaml").read_text(encoding="utf-8"))
        self.assertIsNotNone(tests)
        self.assertIn("unittest", tests.group(0))
        self.sh('git add -A && git commit -qm "chore: adopt aidd"')
        # The agent works on a branch and checks the route before its first edit.
        self.sh("git switch -q -c discount")
        route = self.sh(blocks(step(self.section, 3), "sh")[0])
        self.assertIn("minor", route)
        (self.home / "app" / "discount.py").write_text("def discount(total, percent):\n    return total * (100 - percent) / 100\n", encoding="utf-8")
        (self.home / "tests" / "test_discount.py").write_text(
            "import unittest\nfrom app.discount import discount\n\n\nclass Discount(unittest.TestCase):\n    def test_ten_percent(self):\n"
            "        self.assertEqual(discount(200, 10), 180)\n",
            encoding="utf-8",
        )
        self.sh('git add -A && git commit -qm "feat: apply a percentage discount"')
        self.sh("aidd test")
        self.sh("aidd status")

    def test_every_aidd_command_the_walk_names_parses(self):
        from aidd.cli import parser

        top = parser.build_parser()
        for body in blocks(self.section, "sh"):
            for line in body.splitlines():
                if line.startswith("aidd "):
                    top.parse_args(shlex.split(line)[1:])


if __name__ == "__main__":
    unittest.main()
