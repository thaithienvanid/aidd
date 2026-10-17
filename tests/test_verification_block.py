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

    def test_init_names_the_configured_tests_then_aidd_test_then_the_local_gate(self):
        self.init()
        text = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        block = text.split(config_template.VERIFY_HEADING, 1)[1]
        self.assertIn("paste their output", block)
        for step in ("1. `aidd test`", "2. `aidd gate`"):
            self.assertIn(step, block)
        order = [block.index(s) for s in ("1. `aidd test`", "2. `aidd gate`")]
        self.assertEqual(order, sorted(order))
        self.assertIn("pytest -q", block.split("2. `aidd gate`")[0], "aidd test's step names the config command it runs")
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
        self.assertIn("make test", agents.split("2. `aidd gate`")[0])
        self.assertIn("ruff check 'src dir'", agents.split("2. `aidd gate`")[0])
        self.assertIn("2. `aidd gate`", agents)

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
        (self.root / "GEMINI.md").write_text("# Gemini\n\nOurs.\n", encoding="utf-8")
        adoption.init(self.root, adoption.InitOptions(profile="team", ci="none", links=[], approvers=["@a"], test=["npm", "test"], harnesses=["gemini"]))
        self.assertIn("`npm test`", (self.root / "GEMINI.md").read_text(encoding="utf-8"))
        uninstalling.uninstall(self.root, yes=True)
        self.assertNotIn(config_template.VERIFY_HEADING, (self.root / "GEMINI.md").read_text(encoding="utf-8"))


class SkillSaysDoneMeansVerified(unittest.TestCase):
    def test_skill_and_loop_state_the_rule(self):
        skill = ROOT / ".agents" / "skills" / "aidd"
        for rel in ("SKILL.md", "references/loop.md"):
            text = (skill / rel).read_text(encoding="utf-8")
            for phrase in ("aidd test", "aidd gate", "paste", "fix the code, not the test"):
                self.assertIn(phrase, text, f"{rel}: {phrase}")


class InstructionFileSizeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def warnings(self):
        return [m for lvl, m in doctor_checks.instruction_file_size(self.root) if lvl == "warn"]

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
        self.assertTrue(any(lvl == "warn" and m.startswith("AGENTS.md is 500 lines") for lvl, m in doctor_checks.doctor(self.root)))

    def test_this_repository_and_a_fresh_init_are_within_it(self):
        self.assertEqual(doctor_checks.instruction_file_size(ROOT), [])
        adoption.init(
            self.root, adoption.InitOptions(profile="team", ci="none", links=[], approvers=["@a"], test=["pytest"], harnesses=["claude-code"], team=True)
        )
        self.assertEqual(doctor_checks.instruction_file_size(self.root), [])


if __name__ == "__main__":
    unittest.main()
