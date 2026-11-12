"""The model setting tells the truth. `agents.models` and `agents.effort` change the role files aidd writes, never the files the
aidd-team plugin carries, so init, upgrade, and doctor say so when the plugin carries Claude Code's roles. Doctor also checks the
role files against the config, and the independent-review setting against the models, which only init checked before. The lead
never passes a model the role's agent file does not name."""

import json
import os
import re
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
        return [msg for level, msg in doctor_checks.doctor(self.root) if level == "warning"]

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

    def files(self) -> dict[str, bytes]:
        return {
            p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file() and ".git" not in p.relative_to(self.root).parts
        }

    def stale_count(self) -> int | None:
        """The number of role files the doctor's one warning says are missing or differ, which is the leading number in it; None with no warning."""
        stale = [w for w in self.doctor() if "development team" in w]
        self.assertLessEqual(len(stale), 1, stale)
        return int(re.search(r"\d+", stale[0]).group()) if stale else None

    def test_doctor_names_stale_or_edited_role_files_and_upgrade_keeps_hand_edits(self):
        """The warning is one line at warning level, its count is the number of files the upgrade then changes, and an edited file is kept."""
        self.plugin(False)
        self.adopt()
        self.assertIsNone(self.stale_count())
        cfg = self.root / config.CONFIG_PATH
        cfg.write_text(cfg.read_text(encoding="utf-8") + "\nagents:\n" + MODELS.replace("claude-sonnet-5", "claude-haiku-5"), encoding="utf-8")
        before = self.files()
        counted = self.stale_count()
        self.assertGreater(counted, 1)
        self.assertEqual([lvl for lvl, msg in doctor_checks.doctor(self.root) if "development team" in msg], ["warning"])
        upgrading.upgrade(self.root, yes=True)
        after = self.files()
        self.assertEqual(counted, len([rel for rel in after if rel.startswith((".claude/agents/", ".claude/skills/")) and before.get(rel) != after[rel]]))
        self.assertIsNone(self.stale_count())
        edited = self.root / ".claude" / "agents" / "aidd-developer.md"
        hand_edited = edited.read_text(encoding="utf-8").replace("model: ", "model: x-", 1)
        edited.write_text(hand_edited, encoding="utf-8")
        self.assertEqual(self.stale_count(), 1)
        upgrading.upgrade(self.root, yes=True)
        self.assertEqual(edited.read_text(encoding="utf-8"), hand_edited)

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
