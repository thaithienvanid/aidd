"""This repository's own aidd setup.

The maintainer runs the three Claude Code plugins for their user, so the skill comes from the aidd plugin alone (no
second copy linked into `.claude/skills/`). The session hooks run, at the level the profile sets. Codex and OpenCode V2 run aidd's guard in this repository, as `aidd init` wires them.
"""

import tomllib
import unittest

from helpers import ROOT


class RepoSetupTests(unittest.TestCase):
    def test_a1_the_skill_comes_from_the_plugin_alone(self):
        link = ROOT / ".claude" / "skills" / "aidd"
        self.assertFalse(link.exists() or link.is_symlink(), "a second copy of the skill, beside the aidd plugin's")

    def test_a4_the_sdist_carries_the_new_hook_files(self):
        include = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
        for folder in (".codex/", ".opencode/"):
            with self.subTest(folder=folder):
                self.assertIn(folder, include)


if __name__ == "__main__":
    unittest.main()
