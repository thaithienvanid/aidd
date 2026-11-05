"""The full-material arm of the role evals: the agent file, the aidd skill, and the skills it preloads, against the agent file alone (`--with-skills`)."""

import json
import shlex
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT
from helpers import run_eval_cli as run

from aidd.evals import run_log, suites

SCENARIOS = """
scenario:
  - id: r1
    role: reviewer
    prompt: Review this diff.
    fixture: "query = 'SELECT * FROM t WHERE id = ' + user_id"
    decisions: [block, pass]
    expected: {decision: block}
"""
# Saves the prompt it receives, and ends with the six-line handoff note and a decision.
AGENT = """
import pathlib, sys
pathlib.Path(sys.argv[1]).write_text(sys.stdin.read(), encoding="utf-8")
print("Done: x\\nNext role: y\\nNeeds: none\\nStopped at: none\\nBy: reviewer\\nSpend: unknown\\nDecision: block")
"""
SCENARIO = {"role": "reviewer", "prompt": "Review.", "fixture": "x = 1"}


class PromptTests(unittest.TestCase):
    def test_every_agent_file_preloads_skills_that_resolve(self):
        roles = sorted(p.stem for p in (ROOT / "plugins" / "aidd-team" / "agents").glob("*.md"))
        self.assertTrue(roles)
        for role in roles:
            with self.subTest(role):
                names = suites.role_skill_names(role)
                self.assertEqual((names[0], len(names) == len(set(names))), ("aidd:aidd", True))
                self.assertEqual(suites.role_skills(role).count("## Skill: "), len(names))

    def test_the_arms_differ_only_in_the_skills_they_add(self):
        plain = suites.role_prompt(SCENARIO)
        full = suites.role_prompt(SCENARIO, skills=True)
        skill = suites.role_skills("reviewer")
        cases = {
            "the agent file alone": (plain, [suites.role_playbook("reviewer")], ["## Skill: "]),
            "the full material": (full, [suites.role_playbook("reviewer"), "## Skill: aidd:aidd", skill], []),
            "the control, which skills never reach": (suites.role_prompt(SCENARIO, material=False, skills=True), [], ["## Skill: ", "## Playbook"]),
        }
        for name, (prompt, has, lacks) in cases.items():
            with self.subTest(name):
                self.assertTrue(all(x in prompt for x in has))
                self.assertFalse(any(x in prompt for x in lacks))
        self.assertGreater(len(full), len(plain) + len(skill) - 1)

    def test_a_skill_that_does_not_resolve_is_an_error_naming_it_and_the_next_step(self):
        for name in ("aidd-team:no-such-skill", "other:aidd", "aidd"):
            with self.subTest(name):
                with self.assertRaisesRegex(ValueError, f"cannot find the skill '{name}'.*name `aidd:aidd`.*`skills:` of plugins/aidd-team/agents"):
                    suites.skill_file(name)

    def test_the_readme_keeps_the_arms_apart_and_says_what_the_full_arm_leaves_out(self):
        text = (ROOT / "evals" / "roles" / "README.md").read_text(encoding="utf-8")
        for needed in (
            "converge",
            "--setting-sources project",
            "--strict-mcp-config",
            "--disable-slash-commands",
            '--tools ""',
            "leaves out the `references/` files",
        ):
            with self.subTest(needed):
                self.assertIn(needed, text)


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        (self.base / "roles").mkdir()
        (self.base / "roles" / "scenarios.yaml").write_text(SCENARIOS, encoding="utf-8")
        (self.base / "agent.py").write_text(AGENT, encoding="utf-8")
        self.seen = self.base / "prompt.txt"
        self.cmd = shlex.join([sys.executable, str(self.base / "agent.py"), str(self.seen)])

    def tearDown(self):
        self.tmp.cleanup()

    def roles(self, *extra: str) -> tuple[int, str, dict]:
        record = self.base / "runs.jsonl"
        record.unlink(missing_ok=True)
        code, out = run("eval", "roles", "--scenarios", str(self.base / "roles"), "--agent-command", self.cmd, "--record", str(record), *extra)
        (line,) = [json.loads(x) for x in record.read_text(encoding="utf-8").splitlines()]
        return code, out, line

    def test_with_skills_sends_them_and_records_the_arm_with_its_own_material(self):
        code, out, plain = self.roles()
        self.assertEqual(code, 0, out)
        self.assertNotIn("## Skill: ", self.seen.read_text(encoding="utf-8"))
        code, out, full = self.roles("--with-skills")
        self.assertEqual(code, 0, out)
        self.assertIn("## Skill: aidd:aidd", self.seen.read_text(encoding="utf-8"))
        self.assertEqual((plain["options"], full["options"]), ({}, {"skills": True}))
        self.assertNotEqual(plain["material_sha256"], full["material_sha256"])

    def test_the_report_finds_the_arms_material_fresh(self):
        _, _, full = self.roles("--with-skills")
        top = self.base.resolve()
        run_record = {**full, "cases": "roles"}
        self.assertEqual(run_log.current_material(run_record, top), full["material_sha256"])
        no_option = {**run_record, "options": {}}
        self.assertNotEqual(run_log.current_material(no_option, top), full["material_sha256"])

    def test_the_skills_are_part_of_the_material_files(self):
        with_skills = run_log.material_files("roles", self.base / "roles", skills=True)
        without = run_log.material_files("roles", self.base / "roles")
        added = {p.parent.name for p in set(with_skills) - set(without)}
        self.assertIn("code-review", added)
        self.assertEqual(len(with_skills), len(set(with_skills)))

    def test_with_skills_is_for_the_roles_suite_only(self):
        for suite in ("routing", "tasks", "report", "standards"):
            with self.subTest(suite):
                code, out = run("eval", suite, "--with-skills")
                self.assertEqual(code, 2, out)
                self.assertIn("use it with the roles suite", out)


if __name__ == "__main__":
    unittest.main()
