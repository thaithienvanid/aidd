"""One suite run per head for each independent reader (INIT-1; CHANGELOG 1.0.0).

Text tests over the real files, nothing mocked: the block `aidd init` writes (`verification_block`), the skill, the loop,
the roles file, and the aidd-team command and agent files. They read what an agent is told to do, not what it does.

Test names carry the Acceptance id (A1-A8) or the security test id (S1-S5) they were written for. Tests named "guard" pass on
the base commit on purpose: they keep a skip case from being lost while the wording changes.

Step 5 of implement.md is split into clauses (a newline, a full stop and a space, or a semicolon and a space). A clause that
sends a head back to step 3 says "step 3"; a clause that runs `aidd test` does not. The tests judge each finding code by
the clause that names it.
"""

import json
import re
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd.cli import parser
from aidd.setup import config_template

SKILL = ROOT / ".agents" / "skills" / "aidd"
TEAM = ROOT / "plugins" / "aidd-team"

RERUN_CODES = ("tests.no_evidence", "tests.evidence_other_head", "tests.evidence_other_base", "tests.evidence_partial", "red_green.no_red_run")
HAND_WRITTEN_CODES = ("tests.evidence_invalid", "tests.evidence_schema")
BACK_TO_STEP_3 = ("tests.failed", "tests.flaky")
CODE = re.compile(r"\b(?:tests|red_green)\.[a-z_]+\b")
# Intent patterns: each states the condition it proves and accepts the harmless rewordings of it. Stable identifiers
# (finding codes, commands, flags, file and config names) are pinned literally elsewhere.
NO_TESTS = r"(?i)\bno `?tests?`?\b|\bnone\b"
ONE_FULL_RUN_ON_THE_FINAL_HEAD = r"(?i)\b(once|one|single|final|last)\b"
A_SINGLE_TEST_FILE = r"(?i)\b(one|single|a|one test)\b[^.]*\bfile\b|test file"
THE_DIRECT_RUN_IS_NAMED = r"(?i)direct|yourself|by hand|run them"
OWN_RUN_OF_THE_VERIFIER = r"(?i)\bown\b|\bindependent"
BUILDERS_EVIDENCE_IS_NOT_THE_RESULT = r"(?i)\b(never|not|no)\b[^.]*\b(builders?|developers?)'?s?\b[^.]*evidence|evidence[^.]*\b(never|not)\b"
THE_SKIP_IGNORES_PROSE = r"(?i)\b(never|not|no)\b[^.]*(handoff|chat|note|evidence\.json|evidence file)"
THE_TREE_IS_CLEAN = r"(?i)prints nothing|clean|empty|no output"
A_FINDING_IS_REPORTED = r"(?i)finding|report|flag"
THE_SUITE_RUNS_FOR_A_CHANGE_WITHOUT_A_SPEC = r"(?i)\b(no|without|only for)\b[^.]*\b(Spec|Change Request)\b"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def numbered_item(text: str, number: int, *, last: bool = False) -> str:
    """The numbered list item `number`, with its continuation lines and sub-bullets, up to the next item or heading.
    A command file holds a generated list of rules above its own steps, so `last` takes the final item of that number."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if re.match(rf"\s*{number}\. ", line)]
    start = starts[-1] if last else starts[0]
    indent = len(lines[start]) - len(lines[start].lstrip())
    out = [lines[start]]
    for line in lines[start + 1 :]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent and re.match(r"\s*(\d+\.|#|<!--)", line):
            break
        out.append(line)
    return "\n".join(out)


def implement_step(number: int) -> str:
    return numbered_item(read(TEAM / "commands" / "implement.md"), number, last=True)


def clauses(text: str) -> list[str]:
    return [c for c in re.split(r"\n|(?<=\.)\s+|;\s", text) if c.strip()]


def playbook(rel: str) -> str:
    return read(TEAM / "agents" / rel).split("## Playbook", 1)[1].split("## Stop and hand back", 1)[0]


def hard_rule_9() -> str:
    return numbered_item(read(SKILL / "SKILL.md"), 9)


def roles_rule() -> str:
    """The loop.digest rule "Done means verified", as roles.json holds it."""
    found: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("rule"), str) and node["rule"].startswith("Done means verified"):
                found.append(node["rule"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(json.loads(read(ROOT / "schemas" / "roles.json")))
    assert len(found) == 1, found
    return found[0]


def loop_implement() -> str:
    return read(SKILL / "references" / "loop.md").split("**Implement.**", 1)[1].split("**Verify.**", 1)[0]


class Repo:
    """A repository root holding only a `.aidd/config.yaml`, the way `aidd init` leaves it, for `verification_block`."""

    def __init__(self, tests: list[tuple[str, list[str], list[str] | None]] | None):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        cfg = self.root / ".aidd" / "config.yaml"
        cfg.parent.mkdir(parents=True)
        text = config_template.config_text(config_template.ConfigTemplate("team", approvers=["@org/leads"], test=None))
        if tests:
            lines = ["tests:"]
            for name, command, when in tests:
                lines += [f"  - name: {name}", f"    command: [{', '.join(command)}]"]
                if when:
                    lines.append(f"    when_changed: [{', '.join(when)}]")
            text = text.rstrip("\n") + "\n\n" + "\n".join(lines) + "\n"
        cfg.write_text(text, encoding="utf-8")

    def block(self) -> str:
        return config_template.verification_block(config_template.configured_tests(self.root))

    def close(self):
        self.tmp.cleanup()


def steps(block: str) -> list[str]:
    return re.findall(r"(?m)^\d+\. (.*)$", block)


class GeneratedBlockTests(unittest.TestCase):
    def block(self, tests):
        repo = Repo(tests)
        self.addCleanup(repo.close)
        return repo.block()

    def test_a1_aidd_test_is_the_run_of_the_configured_suite_and_no_step_runs_it_again(self):
        block = self.block([("unit", ["pytest", "-q"], None)])
        listed = steps(block)
        aidd_test = [s for s in listed if s.startswith("`aidd test`")]
        self.assertEqual(len(aidd_test), 1, block)
        self.assertIn("pytest -q", aidd_test[0], "the step names the config command that aidd test runs")
        self.assertFalse([s for s in listed if s.startswith("`pytest -q`")], f"a step still runs the suite directly:\n{block}")
        self.assertTrue(listed[-1].startswith("`aidd gate`"), block)

    def test_a1_the_paste_is_aidd_tests_result_lines_with_their_logs_and_its_evidence_line(self):
        block = self.block([("unit", ["pytest", "-q"], None)])
        self.assertIn("evidence:", block)

    def test_a2_guard_a_when_changed_test_is_still_named_in_the_block(self):
        block = self.block([("unit", ["pytest", "-q"], None), ("lint", ["ruff", "check", "src"], ["src/**"])])
        self.assertIn("ruff check src", block)

    def test_a2_the_block_names_the_skip_cases_aidd_test_may_leave_a_test_out_of(self):
        block = self.block([("unit", ["pytest", "-q"], None), ("lint", ["ruff", "check", "src"], ["src/**"])])
        self.assertIn("smoke", block, "emergency route: only the smoke tests run")
        self.assertIn("config.yaml", block, "a change to the tests entry is not yet in force")
        self.assertRegex(block, r"(?i)when_changed|does not select|not selected", "a test this diff does not select")

    def test_a2_a_when_changed_test_gets_its_own_direct_run_line_apart_from_the_aidd_test_step(self):
        block = self.block([("unit", ["pytest", "-q"], None), ("lint", ["ruff", "check", "src"], ["src/**"])])
        own = [s for s in block.splitlines() if "ruff check src" in s and not re.match(r"\d+\. `aidd test`", s)]
        self.assertTrue(any(re.search(THE_DIRECT_RUN_IS_NAMED + r"|run it|select", s) for s in own), f"no line of its own for the when_changed test:\n{block}")

    def test_s5_guard_a_config_with_no_tests_keeps_the_direct_run_fallback(self):
        block = self.block(None)
        self.assertIn("the repository's tests (none configured yet: add `tests` to `.aidd/config.yaml`)", block)
        self.assertIn("`aidd test`", block)
        self.assertIn("`aidd gate`", block)


class HelpRowTests(unittest.TestCase):
    def test_a4_the_everyday_aidd_test_row_names_the_final_head_and_the_partial_runs_between_steps(self):
        (row,) = [when for typed, _, when in parser.EVERYDAY if typed == "`aidd test`"]
        self.assertRegex(row, ONE_FULL_RUN_ON_THE_FINAL_HEAD)
        self.assertRegex(row, r"--no-red|--changed")


class OneRunOnAnUnchangedHeadTests(unittest.TestCase):
    def test_a3_step_5_reads_the_gate_before_it_runs_aidd_test(self):
        step = implement_step(5)
        self.assertIn("aidd gate --spec specs/<ID>.md --json", step)
        self.assertLess(step.index("aidd gate"), step.index("aidd test"), "step 5 still runs aidd test first")

    def test_a3_step_5_runs_aidd_test_when_merges_moved_the_head(self):
        self.assertIn("tests.evidence_other_head", implement_step(5), "a merge of parallel Task branches makes the evidence name another head")

    def test_a3_guard_step_4_still_runs_aidd_test_after_each_merge(self):
        self.assertRegex(implement_step(4), r"`aidd test --spec specs/<ID>.md` after each merge")

    def test_a3_the_done_means_verified_rule_asks_for_aidd_test_and_aidd_gate_once_on_the_final_head(self):
        for where, rule in (("roles.json", roles_rule()), ("SKILL.md", hard_rule_9())):
            self.assertIn("`aidd test`", rule, where)
            self.assertIn("`aidd gate`", rule, where)
            self.assertRegex(rule, ONE_FULL_RUN_ON_THE_FINAL_HEAD, where)

    def test_a3_this_repositorys_agents_md_runs_the_suite_directly_only_for_a_change_without_a_spec(self):
        text = read(ROOT / "AGENTS.md").split("## Verifying your work", 1)[1]
        self.assertRegex(numbered_item(text, 1), THE_SUITE_RUNS_FOR_A_CHANGE_WITHOUT_A_SPEC)


class RunsBetweenStepsTests(unittest.TestCase):
    def assert_partial_runs_then_one_full_run(self, text: str, where: str):
        self.assertRegex(text, r"--no-red", where)
        self.assertRegex(text, r"--changed", where)
        self.assertRegex(text, A_SINGLE_TEST_FILE, where)
        self.assertRegex(text, ONE_FULL_RUN_ON_THE_FINAL_HEAD, where)

    def test_a4_the_developers_playbook_names_the_partial_runs_and_one_full_run_on_the_final_head(self):
        self.assert_partial_runs_then_one_full_run(numbered_item(playbook("developer.md"), 6), "developer.md Playbook 6")

    def test_a4_the_loops_implement_step_names_the_partial_runs_and_one_full_run_on_the_final_head(self):
        self.assert_partial_runs_then_one_full_run(loop_implement(), "loop.md Implement")

    def test_a4_guard_the_implement_done_conditions_are_word_for_word(self):
        text = loop_implement()
        for line in (
            "- the diff stays inside the Task's `scope`, and no test file changed",
            "- every applicable command exits 0 on the head",
            "- every `new_behavior` command fails on base (a non-zero exit other than 126 or 127) and passes on head",
        ):
            self.assertIn(line, text)


class VerifierIndependenceTests(unittest.TestCase):
    def assert_own_run_never_the_builders(self, text: str, where: str):
        self.assertIn("`aidd test", text, where)
        self.assertRegex(text, OWN_RUN_OF_THE_VERIFIER, where)
        self.assertRegex(text, BUILDERS_EVIDENCE_IS_NOT_THE_RESULT, where)

    def test_s1_a5_the_verifier_playbook_runs_its_own_aidd_test_once_and_never_uses_the_builders_evidence(self):
        self.assert_own_run_never_the_builders(numbered_item(playbook("verifier.md"), 2), "verifier.md Playbook 2")

    def test_s1_a5_the_verify_command_step_2_runs_the_verifiers_own_run_and_never_the_builders_evidence(self):
        self.assert_own_run_never_the_builders(numbered_item(read(TEAM / "commands" / "verify.md"), 2, last=True), "verify.md step 2")

    def test_a5_the_verifier_runs_no_direct_run_of_a_suite_that_aidd_test_includes(self):
        self.assertRegex(numbered_item(playbook("verifier.md"), 2), r"(?i)direct|skips")


class StepFiveAllowListTests(unittest.TestCase):
    def test_s2_a6_the_five_re_run_codes_run_aidd_test_and_are_not_in_a_step_3_clause(self):
        step = implement_step(5)
        for code in RERUN_CODES:
            cs = [c for c in clauses(step) if code in c]
            self.assertTrue(cs, f"step 5 does not name {code}")
            self.assertTrue(any("aidd test" in c and "step 3" not in c for c in cs), f"{code} does not lead to an aidd test run")

    def test_s2_a6_a_failed_or_flaky_head_goes_back_to_step_3_with_no_re_run(self):
        step = implement_step(5)
        for code in BACK_TO_STEP_3:
            cs = [c for c in clauses(step) if code in c]
            self.assertTrue(cs, f"step 5 does not name {code}")
            for c in cs:
                self.assertIn("step 3", c, f"{code} must send the head back to step 3")
                self.assertNotRegex(c, r"(?i)run `aidd test", f"{code} must not lead to a re-run")

    def test_s2_a6_no_other_code_leads_to_an_aidd_test_run(self):
        allowed = set(RERUN_CODES) | set(HAND_WRITTEN_CODES)
        for c in clauses(implement_step(5)):
            if "step 3" in c or "aidd test" not in c:
                continue
            self.assertFalse(set(CODE.findall(c)) - allowed, f"a clause re-runs on a code outside the allow-list: {c}")

    def test_s2_a6_a_possibly_hand_written_evidence_file_is_reported_then_aidd_test_runs_once(self):
        step = implement_step(5)
        for code in HAND_WRITTEN_CODES:
            cs = [c for c in clauses(step) if code in c]
            self.assertTrue(cs, f"step 5 does not name {code}")
            self.assertFalse(any("step 3" in c for c in cs), f"{code} must not send the head back: the file is reported, then aidd test runs once")

    def test_s2b_a6_every_finding_code_implement_names_is_declared_in_the_rulebook(self):
        rulebook = read(ROOT / "src" / "aidd" / "gate" / "rulebook.py")
        named = set(CODE.findall(implement_step(5)))
        self.assertTrue(named >= set(RERUN_CODES), named)
        for code in sorted(named):
            self.assertIn(f'"{code}"', rulebook, f"{code} is not a finding code of the rulebook")


class SkipRestsOnTheGateTests(unittest.TestCase):
    def test_s3_a7_the_skip_reads_aidd_gate_json_finding_codes_never_a_note_chat_or_the_evidence_file(self):
        step = implement_step(5)
        self.assertIn("--json", step)
        self.assertRegex(step, THE_SKIP_IGNORES_PROSE)


class DirtyTreeTests(unittest.TestCase):
    def test_s4_a8_step_5_skips_only_on_a_clean_git_status_porcelain(self):
        step = implement_step(5)
        self.assertIn("git status --porcelain", step)
        self.assertRegex(step, THE_TREE_IS_CLEAN)
        self.assertTrue(any("push" in c for c in clauses(step) if "git status --porcelain" in c), "the clean tree is the condition of the push without a run")

    def test_s4_a8_a_dirty_tree_runs_aidd_test_once(self):
        self.assertRegex(implement_step(5), r"(?i)dirty tree|uncommitted|untracked")

    def test_s4_a8_the_verifier_reports_dirty_paths_as_a_finding(self):
        text = playbook("verifier.md")
        self.assertIn("git status --porcelain", text)
        self.assertRegex(text, A_FINDING_IS_REPORTED)


class DirectRunStaysTests(unittest.TestCase):
    """A2 rows a-d in the skill and in the roles rule, in the words each text uses for the four skip cases."""

    def test_a2_hard_rule_9_names_the_four_cases_where_the_direct_run_stays(self):
        rule = hard_rule_9()
        self.assertIn("when_changed", rule)
        self.assertIn("smoke", rule)
        self.assertIn("config.yaml", rule)
        self.assertRegex(rule, NO_TESTS)

    def test_s5_hard_rule_9_and_the_roles_rule_keep_the_direct_run_for_a_config_with_no_tests(self):
        for where, rule in (("SKILL.md", hard_rule_9()), ("roles.json", roles_rule())):
            self.assertRegex(rule, THE_DIRECT_RUN_IS_NAMED, where)
            self.assertRegex(rule, NO_TESTS, where)


if __name__ == "__main__":
    unittest.main()
