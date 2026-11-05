"""This repository's own aidd setup.

The maintainer runs the three Claude Code plugins for their user, so the skill comes from the aidd plugin alone (no
second copy linked into `.claude/skills/`). aidd wires no hook: each harness's own ask rules hold the `ask` actions, Claude Code's in `.claude/settings.json`.
"""

import tomllib
import unittest

from helpers import ROOT

from aidd import config, risk


class RepoSetupTests(unittest.TestCase):
    def test_a1_the_skill_comes_from_the_plugin_alone(self):
        link = ROOT / ".claude" / "skills" / "aidd"
        self.assertFalse(link.exists() or link.is_symlink(), "a second copy of the skill, beside the aidd plugin's")

    def test_a4_the_sdist_carries_each_harness_files(self):
        include = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
        for folder in (".codex/", ".opencode/", ".claude/settings.json"):
            with self.subTest(folder=folder):
                self.assertIn(folder, include)

    def test_p4_each_harness_here_has_the_ask_rules_aidd_writes_now(self):
        """aidd runs on itself: Claude Code, Codex, and OpenCode here ask before what the risk rules say to ask before."""
        cfg = config.load_file(config.CONFIG_PATH, str(ROOT))
        patterns = risk.harness_patterns(risk.rule_set(cfg), "main")
        for key in ("claude-code", "codex", "opencode"):
            with self.subTest(harness=key):
                self.assertEqual(risk.apply_harness_rules(ROOT, config.HARNESSES[key].ask_rules, patterns, write=False), [], "run the ask-rule writer for it")


if __name__ == "__main__":
    unittest.main()
