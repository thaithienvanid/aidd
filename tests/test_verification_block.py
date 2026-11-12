"""Verify before "done": the block `aidd init` writes into AGENTS.md, its removal, and the instruction-file size check."""

import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd.setup import doctor_checks
from aidd.setup import uninstalling
from aidd.setup import adoption
from aidd.setup import config_template

HOUSE = "# Agents\n\n## House rules\n\nUse pnpm.\n"


class VerificationBlockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def init(self, **kw):
        kw.setdefault("test", ["pytest", "-q"])
        return adoption.init(self.root, adoption.InitOptions(profile="team", ci="none", links=[], approvers=["@org/leads"], harnesses=[], **kw))

    def test_init_names_the_configured_tests_in_aidd_tests_step(self):
        self.init()
        text = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        block = text.split(config_template.VERIFY_HEADING, 1)[1]
        self.assertIn("paste their output", block)
        self.assertIn("1. `aidd test`", block)
        self.assertNotIn("2. ", block, "one step: aidd test runs the suite and the Spec's tests")
        self.assertIn("pytest -q", block.split("1. `aidd test`")[1], "aidd test's step names the config command it runs")
        self.assertNotIn("`pytest -q`: the repository's tests", block, "no step runs the suite a second time")
        self.assertIn("fix the code, not the test", block)
        self.assertIn("never skip, weaken, or delete a failing test", block)
        # Inside aidd's marked section, so it goes wherever that section goes.
        self.assertLess(text.index(adoption.AGENTS_MARK), text.index(config_template.VERIFY_HEADING))

    def test_the_block_stays_short(self):
        self.init()
        block = (self.root / "AGENTS.md").read_text(encoding="utf-8").split(config_template.VERIFY_HEADING, 1)[1]
        self.assertLess(len(block.splitlines()), 15)

    def test_without_a_test_command_it_says_none_is_configured(self):
        self.init(test=None)
        self.assertIn("none configured yet: add `tests`", (self.root / "AGENTS.md").read_text(encoding="utf-8"))

    def test_an_existing_config_supplies_every_tests_command(self):
        cfg = self.root / ".aidd" / "config.yaml"
        cfg.parent.mkdir(parents=True)
        text = config_template.config_text(config_template.ConfigTemplate("team", approvers=["@org/leads"], test=["make", "test"]))
        text = text.replace("    command: [make, test]\n", "    command: [make, test]\n  - name: lint\n    command: [ruff, check, src dir]\n", 1)
        self.assertIn("name: lint", text)
        cfg.write_text(text, encoding="utf-8")
        self.init(test=None)
        agents = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("1. `aidd test`", agents)
        step = agents.split("1. `aidd test`", 1)[1]
        self.assertIn("make test", step)
        self.assertIn("ruff check 'src dir'", step)

    def test_a_command_that_runs_in_a_folder_is_told_with_its_folder(self):
        """A command an agent runs by hand runs where `aidd test` runs it, so the block names the folder (`runs_in`) beside it."""
        cfg = self.root / ".aidd" / "config.yaml"
        cfg.parent.mkdir(parents=True)
        text = config_template.config_text(config_template.ConfigTemplate("team", approvers=["@org/leads"], test=["make", "test"]))
        text = text.replace(
            "    command: [make, test]\n",
            "    command: [make, test]\n  - name: api\n    command: [npm, test]\n    runs_in: packages/api\n    when_changed: [packages/api/**]\n"
            "  - name: web\n    command: [npm, test]\n    runs_in: packages/web\n",
            1,
        )
        cfg.write_text(text, encoding="utf-8")
        step = config_template.verification_block(config_template.configured_tests(self.root))
        self.assertIn("runs `make test`, `npm test` in `packages/web` and each test this diff selects", step)
        self.assertIn("`npm test` in `packages/api`: run it yourself when this diff does not select it", step)

    def test_uninstall_removes_the_block_with_the_rest_of_the_section(self):
        (self.root / "AGENTS.md").write_text(HOUSE, encoding="utf-8")
        self.init()
        self.assertIn(config_template.VERIFY_HEADING, (self.root / "AGENTS.md").read_text(encoding="utf-8"))
        uninstalling.uninstall(self.root, yes=True)
        self.assertEqual((self.root / "AGENTS.md").read_text(encoding="utf-8"), HOUSE)

    def test_uninstall_removes_an_agents_md_init_wrote(self):
        self.init()
        uninstalling.uninstall(self.root, yes=True)
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_a_pointer_file_carries_the_block_and_loses_it_on_uninstall(self):
        pointer = self.root / ".github" / "copilot-instructions.md"
        pointer.parent.mkdir()
        pointer.write_text("# Project\n\nOurs.\n", encoding="utf-8")
        adoption.init(self.root, adoption.InitOptions(profile="team", ci="none", links=[], approvers=["@a"], test=["npm", "test"], harnesses=["copilot"]))
        self.assertIn("`npm test`", pointer.read_text(encoding="utf-8"))
        uninstalling.uninstall(self.root, yes=True)
        self.assertNotIn(config_template.VERIFY_HEADING, pointer.read_text(encoding="utf-8"))

    def test_claude_codes_file_imports_the_block_once_and_loses_the_import_on_uninstall(self):
        (self.root / "CLAUDE.md").write_text("# Project\n\nOurs.\n", encoding="utf-8")
        adoption.init(self.root, adoption.InitOptions(profile="team", ci="none", links=[], approvers=["@a"], test=["npm", "test"], harnesses=["claude-code"]))
        self.assertIn("@AGENTS.md", (self.root / "CLAUDE.md").read_text(encoding="utf-8"))
        self.assertNotIn("`npm test`", (self.root / "CLAUDE.md").read_text(encoding="utf-8"))  # the block loads once, from AGENTS.md
        self.assertIn("`npm test`", (self.root / "AGENTS.md").read_text(encoding="utf-8"))
        uninstalling.uninstall(self.root, yes=True)
        self.assertEqual((self.root / "CLAUDE.md").read_text(encoding="utf-8"), "# Project\n\nOurs.\n")


class SkillSaysDoneMeansVerified(unittest.TestCase):
    def test_skill_and_loop_state_the_rule(self):
        skill = ROOT / ".agents" / "skills" / "aidd"
        # SKILL.md owns the rule, and graph.md always loads with it, so the loop names the command and does not restate the rule.
        text = (skill / "SKILL.md").read_text(encoding="utf-8")
        for phrase in ("aidd test", "paste", "fix the code, not the test"):
            self.assertIn(phrase, text.lower(), f"SKILL.md: {phrase}")
        self.assertIn("aidd test", (skill / "references" / "graph.md").read_text(encoding="utf-8").lower())


class InstructionFileSizeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def warnings(self):
        return [m for lvl, m in doctor_checks.instruction_file_size(self.root) if lvl == "warning"]

    def test_within_the_budget_says_nothing(self):
        (self.root / "AGENTS.md").write_text("line\n" * doctor_checks.INSTRUCTION_MAX_LINES, encoding="utf-8")
        (self.root / "CLAUDE.md").write_text("x" * 100 + "\n", encoding="utf-8")
        self.assertEqual(self.warnings(), [])

    def test_too_many_lines_warns(self):
        (self.root / "AGENTS.md").write_text("line\n" * (doctor_checks.INSTRUCTION_MAX_LINES + 1), encoding="utf-8")
        (w,) = self.warnings()
        self.assertTrue(w.startswith("AGENTS.md is 201 lines"), w)

    def test_too_many_bytes_in_few_lines_warns(self):
        (self.root / "CLAUDE.md").write_text("x" * (doctor_checks.INSTRUCTION_MAX_BYTES + 1), encoding="utf-8")
        (w,) = self.warnings()
        self.assertTrue(w.startswith("CLAUDE.md is 1 lines"), w)

    def test_doctor_reports_it(self):
        (self.root / "AGENTS.md").write_text("aidd\n" * 500, encoding="utf-8")
        self.assertTrue(any(lvl == "warning" and m.startswith("AGENTS.md is 500 lines") for lvl, m in doctor_checks.doctor(self.root)))

    def test_this_repository_and_a_fresh_init_are_within_it(self):
        self.assertEqual(doctor_checks.instruction_file_size(ROOT), [])
        adoption.init(
            self.root, adoption.InitOptions(profile="team", ci="none", links=[], approvers=["@a"], test=["pytest"], harnesses=["claude-code"], aidd_team=True)
        )
        self.assertEqual(doctor_checks.instruction_file_size(self.root), [])


if __name__ == "__main__":
    unittest.main()
