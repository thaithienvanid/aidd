"""`aidd init --orca` writes the orca.yaml that docs/ORCA.md documents, never replaces one, and writes nothing without the flag."""

import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, aidd_subprocess, git

from aidd.setup import adoption, orca_file


def options(**more):
    return adoption.InitOptions(profile="team", ci="none", links=[], skill=False, approvers=["@x"], harnesses=[], **more)


@unittest.skipUnless(shutil.which("git"), "git is required")
class InitOrcaTests(unittest.TestCase):
    def repo(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        root = Path(d.name)
        git(root, "init", "-q")
        return root

    def test_it_is_written_with_the_flag(self):
        root = self.repo()
        actions = adoption.init(root, options(orca=True))
        text = (root / "orca.yaml").read_text(encoding="utf-8")
        self.assertIn("setup: |\n    aidd doctor\n", text)
        self.assertIn("setupAgentStartupPolicy: wait-for-setup", text)
        self.assertIn("command: aidd list --branch", text)
        wrote = [a for a in actions if a.startswith("wrote    ") and "orca.yaml" in a]
        self.assertEqual(len(wrote), 1, actions)
        self.assertIn("protected path", wrote[0])

    def test_the_documented_file_matches(self):
        docs = (ROOT / "docs" / "ORCA.md").read_text(encoding="utf-8")
        for line in orca_file.ORCA_YAML.splitlines():
            self.assertIn(line, re.sub(r"[ ]+#.*", "", docs), line)

    def test_an_existing_one_is_kept_and_what_it_would_add_is_shown(self):
        root = self.repo()
        (root / "orca.yaml").write_text("scripts:\n  setup: make\n", encoding="utf-8")
        for force in (False, True):
            actions = adoption.init(root, options(orca=True, force=force))
            self.assertEqual((root / "orca.yaml").read_text(encoding="utf-8"), "scripts:\n  setup: make\n")
            (kept,) = [a for a in actions if a.startswith("kept     ") and "orca.yaml" in a]
            self.assertIn("never replaces", kept)
            self.assertIn("aidd list --branch", kept)
            self.assertIn("protected path", kept)

    def test_it_is_not_written_without_the_flag(self):
        root = self.repo()
        adoption.init(root, options())
        self.assertFalse((root / "orca.yaml").exists())

    def test_the_flag_reaches_the_command(self):
        root = self.repo()
        for flag in ([], ["--orca"]):
            aidd_subprocess("init", str(root), "--ci", "none", "--harness", "none", "--no-skill", "--approvers", "@x", "--profile", "team", *flag, cwd=root)
            self.assertEqual((root / "orca.yaml").exists(), bool(flag))


if __name__ == "__main__":
    unittest.main()
