"""The model setting tells the truth. `agents.models` and `agents.effort` change the role files aidd writes, never the files the
aidd-team plugin carries, so init, upgrade, and doctor say so when the plugin carries Claude Code's roles. Doctor also checks the
role files against the config, and the independent-review setting against the models, which only init checked before. The lead
never passes a model the role's agent file does not name."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import git

from aidd import config
from aidd.knowledge import agent_models
from aidd.setup import adoption, doctor_checks, team_install, upgrading

MODELS = '  models:\n    reasoning: "anthropic/claude-opus-5-5"\n    execution: "anthropic/claude-sonnet-5"\n'
TEAM = f"aidd-team@{config.MARKETPLACE}"


class TeamModelsHonest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / "repo"
        self.root.mkdir()
        self.claude_home = Path(tmp.name).resolve() / "claude-home"
        self.claude_home.mkdir()
        env = mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.claude_home)})
        env.start()
        self.addCleanup(env.stop)
        git(self.root, "init", "-q", "-b", "main")

    def plugin(self, on: bool) -> None:
        (self.claude_home / "settings.json").write_text(json.dumps({"enabledPlugins": {TEAM: on}}), encoding="utf-8")

    def adopt(self, agents: str = "", *, team: bool = True) -> list[str]:
        options = adoption.InitOptions(profile="solo", ci="none", links=[], skill=False, harnesses=["claude-code"], approvers=["@me"], aidd_team=team)
        actions = adoption.init(self.root, options)
        if agents:
            cfg = self.root / config.CONFIG_PATH
            cfg.write_text(cfg.read_text(encoding="utf-8") + "\nagents:\n" + agents, encoding="utf-8")
        return actions

    def doctor(self) -> list[str]:
        return [msg for level, msg in doctor_checks.doctor(self.root) if level == "warn"]

    def test_the_setting_is_said_to_do_nothing_only_where_the_plugin_carries_the_roles(self):
        """Table: the plugin on or off, and `agents.models`, `agents.effort`, `agents.max_turns`, some of them, or none set."""
        efforts = "  effort:\n    execution: medium\n"
        for plugin_on, agents, says in (
            (True, MODELS, "agents.models is set"),
            (True, efforts, "agents.effort is set"),
            (True, MODELS + efforts, "agents.models and agents.effort are set"),
            (True, "  max_turns:\n    execution: 150\n", "agents.max_turns is set"),
            (True, MODELS + efforts + "  max_turns:\n    execution: 150\n", "agents.models, agents.effort, and agents.max_turns are set"),
            (True, "", None),
            (False, MODELS, "agents.models is set"),  # the note alone: it is said only where the plugin carries the roles
            (False, "", None),
        ):
            with self.subTest(plugin_on=plugin_on, agents=agents):
                self.plugin(plugin_on)
                (self.root / ".aidd").mkdir(exist_ok=True)
                (self.root / config.CONFIG_PATH).write_text(
                    'aidd_version: "1.0.0"\nprofile: solo\n' + ("agents:\n" + agents if agents else ""), encoding="utf-8"
                )
                note = team_install.models_inert_note(self.root)
                self.assertEqual(note is not None, says is not None, note)
                if says:
                    self.assertTrue(note.startswith(says), note)
                    self.assertIn("aidd init --aidd-team", note)
                self.assertEqual(team_install.team_plugin_carries_roles(self.root), plugin_on)

    def test_doctor_and_upgrade_say_it_when_the_plugin_carries_the_roles(self):
        self.plugin(True)
        self.adopt(MODELS)
        warned = [w for w in self.doctor() if "carries the roles in Claude Code" in w]
        self.assertEqual(len(warned), 1, warned)
        self.assertTrue(any(a.startswith("note     agents.models is set") for a in upgrading.upgrade(self.root)))
        self.plugin(False)
        self.assertEqual([w for w in self.doctor() if "carries the roles in Claude Code" in w], [])

    def test_init_says_it_when_the_config_already_sets_the_models(self):
        self.plugin(True)
        self.adopt(MODELS)
        again = adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], skill=False, harnesses=["claude-code"], aidd_team=True))
        self.assertTrue(any(a.startswith("note     agents.models is set") for a in again), again)

    def test_doctor_names_a_role_file_that_differs_from_the_config_until_upgrade_rewrites_it(self):
        self.plugin(False)
        self.adopt()
        self.assertEqual([w for w in self.doctor() if "delivery team" in w], [])
        cfg = self.root / config.CONFIG_PATH
        cfg.write_text(cfg.read_text(encoding="utf-8") + "\nagents:\n" + MODELS.replace("claude-sonnet-5", "claude-haiku-5"), encoding="utf-8")
        stale = [w for w in self.doctor() if "delivery team" in w]
        self.assertEqual(len(stale), 1, stale)
        self.assertIn("aidd upgrade --yes", stale[0])
        upgrading.upgrade(self.root, yes=True)
        self.assertEqual([w for w in self.doctor() if "delivery team" in w], [])
        edited = self.root / ".claude" / "agents" / "aidd-developer.md"
        edited.write_text(edited.read_text(encoding="utf-8").replace("model: ", "model: x-", 1), encoding="utf-8")
        self.assertEqual(len([w for w in self.doctor() if "delivery team" in w]), 1)

    def test_doctor_and_upgrade_rerun_the_independent_review_check(self):
        self.plugin(False)
        self.adopt("  independent_review: true\n" + MODELS)  # one provider for every role
        warned = [w for w in self.doctor() if "independent_review" in w]
        self.assertEqual(len(warned), 1, warned)
        self.assertFalse(warned[0].startswith("warn"), "doctor's level is the line's, so the line does not repeat it")
        self.assertEqual(len([a for a in upgrading.upgrade(self.root) if "independent_review" in a]), 1)
        cfg = self.root / config.CONFIG_PATH
        cfg.write_text(cfg.read_text(encoding="utf-8").replace("independent_review: true", "independent_review: false"), encoding="utf-8")
        self.assertEqual([w for w in self.doctor() if "independent_review" in w], [])

    def test_a_model_the_claude_code_field_cannot_select_says_the_tier_alias_runs(self):
        self.plugin(False)
        self.adopt('  models:\n    reviewer: "openai/gpt-6-astra"\n')
        files = team_install.team_files(["claude-code"], True, {"reviewer": "openai/gpt-6-astra"})
        reviewer = files[".claude/agents/aidd-reviewer.md"]
        self.assertIn("\nmodel: opus\n# agents.models names openai/gpt-6-astra", reviewer)
        self.assertIn("this role runs `opus`, the tier's default", reviewer)
        self.assertNotIn("the harness's default model runs this role", reviewer)
        self.assertIn("the harness's default model runs this role", agent_models.unsupported_note("openai/gpt-6-astra"))


if __name__ == "__main__":
    unittest.main()
