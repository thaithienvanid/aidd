"""This repository's own aidd setup.

The maintainer runs the three Claude Code plugins for their user, so the skill comes from the aidd plugin alone (no
second copy linked into `.claude/skills/`). aidd wires no hook: each harness's own ask rules hold the `ask` actions, Claude Code's in `.claude/settings.json`.
"""

import json
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
        rs = risk.rule_set(cfg)
        patterns, read_paths = risk.harness_patterns(rs, "main"), risk.harness_read_paths(rs)
        for key in ("claude-code", "codex", "opencode"):
            with self.subTest(harness=key):
                self.assertEqual(
                    risk.apply_harness_rules(ROOT, config.HARNESSES[key].ask_rules, patterns, read_paths=read_paths, write=False),
                    [],
                    f"{key}'s ask rules here lag the risk rules: run `PYTHONPATH=src python3 -m aidd upgrade --yes` "
                    "and commit what it writes. It reads the default branch from origin/HEAD, so first run "
                    "`git remote set-head origin main` when that names another branch",
                )

    def test_s3_a_release_tag_can_be_made_but_never_moved_or_deleted(self):
        ruleset = json.loads((ROOT / ".github" / "rulesets" / "tag.json").read_text(encoding="utf-8"))
        self.assertEqual((ruleset["target"], ruleset["enforcement"]), ("tag", "active"))
        self.assertEqual(ruleset["conditions"]["ref_name"]["include"], ["refs/tags/v*"])
        self.assertEqual({r["type"] for r in ruleset["rules"]}, {"deletion", "non_fast_forward", "update"})
        self.assertEqual(ruleset["bypass_actors"], [], "nobody moves a release tag, the owner included")


if __name__ == "__main__":
    unittest.main()
