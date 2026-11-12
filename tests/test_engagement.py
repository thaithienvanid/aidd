"""Engagement: a model that starts work in a repository set up with aidd always has, in context, one sentence that names the
first command to run (`aidd risk --paths <the paths>`), whichever supported coding agent it is.

The invariant: after `aidd init`, some file that each coding agent reads at session start (its `loads` in `config.harnesses`,
each with its vendor page and the date aidd read it) holds that sentence. Claude Code skips `AGENTS.md` while a `CLAUDE.md`,
`.claude/CLAUDE.md`, or `CLAUDE.local.md` exists, so there the file it reads imports `AGENTS.md` and the block loads once.

A person's Claude Code files in each layout real files take are in tests/test_claude_md_import.py."""

from __future__ import annotations

import dataclasses
import re
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  # the hermetic environment
from budgets import make_room, within
from engagement import BLOCK, BLOCK_CAP, FIRST_COMMAND, OURS, ROOT, UNCONFIRMED, lay_out, options, read_at_start

from aidd import config
from aidd.setup import adoption, doctor_checks, instruction_imports, marked_sections


class TheBlock(unittest.TestCase):
    def test_it_opens_with_the_first_command_and_stays_small(self):
        self.assertTrue(BLOCK.startswith("This repository uses aidd. Before your first edit, run `aidd risk --paths <"), BLOCK[:120])
        self.assertTrue(within(len(BLOCK.encode()), BLOCK_CAP), make_room("the block aidd writes into AGENTS.md", len(BLOCK.encode()), BLOCK_CAP))

    def test_it_says_what_to_do_when_the_command_is_not_on_the_path(self):
        self.assertIn("If `aidd` is not on the PATH, the skill says what to run instead.", BLOCK)

    def test_every_path_it_names_exists_after_init_with_the_skill_and_none_is_named_without_it(self):
        for skill in (True, False):
            with self.subTest(skill=skill), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                adoption.init(root, options("codex", skill=skill))
                text = (root / "AGENTS.md").read_text(encoding="utf-8")
                named = re.findall(r"`(\.agents/[^`]+)`", text)
                self.assertEqual(bool(named), skill, named)
                for rel in named:
                    self.assertTrue((root / rel).is_file(), f"{rel} is named and does not exist")
                self.assertEqual(marked_sections.PLUGIN_PHRASE in text, not skill)
                self.assertIn(FIRST_COMMAND, text)


class TheShortTextsMatchPlainRequests(unittest.TestCase):
    """The skill's description and the MCP server's instructions reach the model in every session, so each names the plain
    first requests and the first command. Each also stays under the smallest size a vendor documents for it, which
    tests/test_harness_sizes.py holds from config.SIZES, with each page and the date it was read."""

    def test_the_mcp_instructions_ask_for_the_risk_check_before_the_first_edit(self):
        from aidd.cli import mcp_server

        self.assertIn("call risk with the paths you plan to change before your first edit", mcp_server.INSTRUCTIONS)

    def test_the_skill_description_names_a_fix_a_feature_and_a_commit(self):
        text = (ROOT / ".agents" / "skills" / "aidd" / "SKILL.md").read_text(encoding="utf-8")
        description = next(line for line in text.splitlines() if line.startswith("description: "))
        for plain in ("bug fix", "feature", "refactor", "commit"):
            self.assertIn(plain, description)


class EveryAgentReadsTheSentence(unittest.TestCase):
    def test_after_init_some_file_each_agent_reads_holds_the_first_command(self):
        for key, harness in config.HARNESSES.items():
            with self.subTest(harness=key), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                adoption.init(root, options(key))
                self.assertIn(FIRST_COMMAND, read_at_start(root, harness))

    def test_the_check_fails_for_an_agent_where_no_file_holds_it(self):
        none = dataclasses.replace(config.HARNESSES["codex"], loads=())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adoption.init(root, options("codex"))
            self.assertNotIn(FIRST_COMMAND, read_at_start(root, none))
            hidden = dataclasses.replace(config.HARNESSES["codex"], loads=(dataclasses.replace(config.HARNESSES["codex"].loads[0], unless=("AGENTS.md",)),))
            self.assertNotIn(FIRST_COMMAND, read_at_start(root, hidden))

    def test_every_agent_names_a_file_with_its_page_and_date_and_the_unconfirmed_ones_are_listed(self):
        for key, harness in config.HARNESSES.items():
            with self.subTest(harness=key):
                self.assertTrue(harness.loads, "no file named: add its `loads` with the vendor page")
                for load in harness.loads:
                    self.assertRegex(load.read, r"^\d{4}-\d{2}-\d{2}$")
                    self.assertTrue(load.source)
        unconfirmed = {k for k, h in config.HARNESSES.items() if not any(load.confirmed for load in h.loads)}
        self.assertEqual(unconfirmed, set(UNCONFIRMED))


class WhatDoctorSays(unittest.TestCase):
    """A file that hides AGENTS.md from Claude Code, with no import, is a warning that names the next step."""

    CASES = {
        "no file": ({}, False),
        "CLAUDE.md that imports": ({"CLAUDE.md": "@AGENTS.md\n"}, False),
        ".claude/CLAUDE.md that imports": ({".claude/CLAUDE.md": "@../AGENTS.md\n"}, False),
        "CLAUDE.md that links": ("link", False),
        "CLAUDE.md with no import": ({"CLAUDE.md": OURS}, True),
        ".claude/CLAUDE.md with no import": ({".claude/CLAUDE.md": OURS}, True),
        "CLAUDE.local.md alone": ({"CLAUDE.local.md": OURS}, True),
        "CLAUDE.local.md and an importing CLAUDE.md": ({"CLAUDE.local.md": "x\n", "CLAUDE.md": "@AGENTS.md\n"}, False),
        "an import in code": ({"CLAUDE.md": "`@AGENTS.md`\n"}, True),
        "the wrong path in .claude/": ({".claude/CLAUDE.md": "@AGENTS.md\n"}, True),
    }

    def test_the_warning_by_layout(self):
        claude = config.HARNESSES["claude-code"]
        for name, (files, warns) in self.CASES.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
                if files == "link":
                    (root / "CLAUDE.md").symlink_to("AGENTS.md")
                else:
                    lay_out(root, files)
                why = instruction_imports.problem(root, claude)
                self.assertEqual(why is not None, warns, why)
                if why:
                    self.assertIn("aidd init", why)
                    self.assertIn("@AGENTS.md", why)

    def test_doctor_warns_for_a_file_that_hides_the_guide_and_is_quiet_once_init_adds_the_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adoption.init(root, options("claude-code"))
            (root / "CLAUDE.local.md").write_text(OURS, encoding="utf-8")
            hidden = [m for level, m in doctor_checks.doctor(root) if "in place of AGENTS.md" in m]
            self.assertEqual([m.split(",")[0] for m in hidden], ["Claude Code reads CLAUDE.local.md in place of AGENTS.md"])
            adoption.init(root, options("claude-code"))
            lines = [(level, m) for level, m in doctor_checks.doctor(root) if "AGENTS.md" in m and "Claude Code" in m]
            self.assertEqual([level for level, _ in lines], ["ok"], lines)

    def test_a_stale_copy_is_told_to_upgrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_text(OURS + "\n" + adoption.agents_snippet(root, True), encoding="utf-8")
            why = instruction_imports.problem(root, config.HARNESSES["claude-code"])
            self.assertIn("aidd upgrade --yes", why or "")


class ReadingAnImport(unittest.TestCase):
    CASES = [
        ("@AGENTS.md", "CLAUDE.md", True),
        ("@./AGENTS.md", "CLAUDE.md", True),
        ("See @AGENTS.md for the rules.", "CLAUDE.md", True),
        ("@AGENTS.md", ".claude/CLAUDE.md", False),
        ("@../AGENTS.md", ".claude/CLAUDE.md", True),
        ("`@AGENTS.md`", "CLAUDE.md", False),
        ("```\n@AGENTS.md\n```", "CLAUDE.md", False),
        ("~~~\n@AGENTS.md\n~~~\n@AGENTS.md", "CLAUDE.md", True),
        ("mail me@AGENTS.md", "CLAUDE.md", False),
        ("@AGENTS.md.bak", "CLAUDE.md", False),
        ("@docs/AGENTS.md", "CLAUDE.md", False),
        ("", "CLAUDE.md", False),
    ]

    def test_it_reads_an_import_as_claude_code_does(self):
        for text, rel, expected in self.CASES:
            with self.subTest(text=text, rel=rel):
                self.assertEqual(instruction_imports.imports_agents_md(text, rel), expected)

    def test_a_hostile_file_is_read_in_well_under_a_second(self):
        import time

        hostile = ["`" * 1_000_000, "@" * 1_000_000, "`a " * 300_000, ("@a`" * 600 + "\n") * 1000, " " * 1_000_000, "@AGENTS.md" + "x" * 1_000_000]
        for text in hostile:
            with self.subTest(text=text[:12]):
                start = time.perf_counter()
                instruction_imports.imports_agents_md(text, "CLAUDE.md")
                instruction_imports.person_imports(text, "CLAUDE.md")
                self.assertLess(time.perf_counter() - start, 1.0)

    def test_the_section_it_writes_is_an_import_it_reads(self):
        for rel in ("CLAUDE.md", ".claude/CLAUDE.md"):
            with self.subTest(rel=rel):
                section = instruction_imports.import_section(rel)
                self.assertTrue(instruction_imports.imports_agents_md(section, rel))
                self.assertFalse(instruction_imports.person_imports(section, rel), "aidd's own section is not the person's import")
                (found,) = marked_sections.sections(section, marked_sections.AGENTS_MARK)
                self.assertTrue(found.closed)


class TheEngagementCases(unittest.TestCase):
    """The pair of plugin cases (evals/plugin/engages-*) starts from files the real `aidd init` wrote, and asks in plain words."""

    CASES = ("engages-on-a-plain-request", "engages-with-a-claude-md")

    def test_each_fixture_leaves_the_files_init_writes_and_the_prompt_names_no_aidd(self):
        from test_flow_cases import seed
        from test_plugin_evals import front_matter

        claude = config.HARNESSES["claude-code"]
        for name in self.CASES:
            case = ROOT / "evals" / "plugin" / name
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                seed(case, work)
                self.assertIn(FIRST_COMMAND, (work / "AGENTS.md").read_text(encoding="utf-8"), "AGENTS.md is the block init writes")
                self.assertTrue((work / ".aidd" / "config.yaml").is_file())
                self.assertEqual(self.CASES.index(name) == 1, (work / "CLAUDE.md").is_file())
                if (work / "CLAUDE.md").is_file():
                    persons = (work / "CLAUDE.md").read_text(encoding="utf-8")
                    self.assertTrue(persons.startswith("# Cart\n"), "the person's own text stays first")
                    self.assertEqual(read_at_start(work, claude).count(FIRST_COMMAND), 1)
                body = front_matter(case / "prompt.md")[1]
                self.assertNotIn("aidd", body.lower())
                self.assertIn("claim:control:risk-before-the-first-edit", front_matter(case / "prompt.md")[0]["tags"])

    def test_both_cases_hold_the_same_trace_grader_so_one_reads_as_the_other(self):
        texts = {(ROOT / "evals" / "plugin" / n / "graders" / "risk-before-the-first-edit.md").read_text(encoding="utf-8") for n in self.CASES}
        self.assertEqual(len(texts), 1)


if __name__ == "__main__":
    unittest.main()
