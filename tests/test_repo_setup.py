"""This repository's own aidd setup.

The maintainer runs the three Claude Code plugins for their user, so the skill comes from the aidd plugin alone (no
second copy linked into `.claude/skills/`). The session hooks run at `balanced`, so the stop reminder and the handoff
note reminder run here too. Codex and OpenCode V2 run aidd's guard in this repository, as `aidd init` wires them.
"""

import json
import tomllib
import unittest

from helpers import ROOT

from aidd.guard import repo_config
from aidd.setup import codex_wiring, opencode_wiring


class RepoSetupTests(unittest.TestCase):
    def test_a1_the_skill_comes_from_the_plugin_alone(self):
        link = ROOT / ".claude" / "skills" / "aidd"
        self.assertFalse(link.exists() or link.is_symlink(), "a second copy of the skill, beside the aidd plugin's")

    def test_a2_the_session_hooks_run_balanced(self):
        cfg = repo_config.load_config(str(ROOT))
        self.assertIsNotNone(cfg)
        self.assertEqual((cfg.raw.get("hooks") or {}).get("level"), "balanced")

    def test_codex_and_grok_are_never_given_claude_codes_own_events(self):
        """SubagentStart is Claude Code's own: the hook file Codex and Grok Build get never names it."""
        from aidd.setup import grok_wiring

        for wiring in (codex_wiring.FILE, grok_wiring.FILE):
            with self.subTest(path=wiring.path):
                self.assertNotIn("SubagentStart", wiring.hook_spec())
                self.assertIn("SubagentStop", wiring.hook_spec())

    def test_a3_codex_runs_the_guard_and_the_session_hooks(self):
        wired = codex_wiring.wired(ROOT)
        self.assertEqual(set(wired), set(codex_wiring.EVENTS))
        for event, sub in codex_wiring.EVENTS.items():
            with self.subTest(event=event):
                self.assertEqual(wired[event], codex_wiring.hook_command(sub))
        json.loads((ROOT / codex_wiring.HOOKS_FILE).read_text(encoding="utf-8"))  # a JSON object Codex reads

    def test_a3_opencode_runs_the_guard_plugin(self):
        self.assertEqual(opencode_wiring.state(ROOT), "current")

    def test_a4_the_sdist_carries_the_new_hook_files(self):
        include = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
        for folder in (".codex/", ".opencode/"):
            with self.subTest(folder=folder):
                self.assertIn(folder, include)


if __name__ == "__main__":
    unittest.main()
