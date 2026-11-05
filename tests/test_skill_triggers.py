"""Trigger cases for eight practice skills, each with four should-load prompts and four near misses.

The picks follow `schemas/roles.json`: the skills the most distinct roles carry or preload, leaving out `context` (it fires at
the start of every step, so no request calls for it). The last pick is a judgment, and the README says so. `debugging` and `resilience` are findings: batch C3 saw neither load on seeded code. The cases are scored
by `tool_used: Skill` with the skill's name, with or without the `aidd-team:` prefix.
"""

import json
import re
import unittest
from collections import Counter

from helpers import ROOT
from test_plugin_evals import front_matter

TEAM = ROOT / "plugins" / "aidd-team"
EVALS = TEAM / "evals"
SKILLS = ("accessible-ui", "debugging", "diagrams", "maintainable-code", "naming", "plain-language", "resilience", "secure-coding")
# The words of each skill's description that name what calls for it. A near miss uses at least one of them and asks for no such task.
TRIGGER_WORDS = {
    "accessible-ui": ("screen", "form", "copy", "focus", "contrast"),
    "debugging": ("test", "bug", "flaky", "broke"),
    "diagrams": ("design", "threat", "plan", "runbook", "picture", "flow"),
    "maintainable-code": ("function", "file", "module", "package", "comment", "docstring"),
    "naming": ("module", "type", "file", "column", "event", "flag", "metric", "component", "token", "label"),
    "plain-language": ("docs", "specs", "runbooks", "messages", "documents"),
    "resilience": ("service", "queue", "provider", "job", "retries", "timeouts", "duplicate"),
    "secure-coding": ("input", "auth", "secrets", "config", "files", "sql", "shell", "crypto"),
}


def roles_carrying() -> Counter:
    """For each practice skill, how many distinct roles carry or preload it."""
    roles = json.loads((ROOT / "schemas" / "roles.json").read_text(encoding="utf-8"))
    return Counter(p for role in roles["roles"].values() for p in set(role.get("practices", [])) | set(role.get("preload", [])))


def description(skill: str) -> str:
    text = (TEAM / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
    return re.search(r'^description: "(.*)"$', text, re.M).group(1).lower()


def cases(prefix: str, skill: str):
    return sorted(EVALS.glob(f"{prefix}-{skill}-*"))


def every_trigger():
    """The 64 development cases and the 8 held-out ones."""
    return sorted(EVALS.glob("loads-*")) + sorted(EVALS.glob("skips-*")) + sorted(EVALS.glob("held-out-loads-*"))


def prompt_of(case) -> str:
    return front_matter(case / "prompt.md")[1].replace("This repository uses aidd.", "").lower()


# What a `loads` prompt asks for, by domain. No domain holds more than a third of them, so a description is not tuned to one kind of project.
DOMAIN = {
    "accessible-ui-grey-contrast": "mobile",
    "accessible-ui-icon-delete": "logistics",
    "accessible-ui-login-form": "identity",
    "accessible-ui-modal-keyboard": "saas",
    "debugging-failing-invoice-test": "commerce",
    "debugging-flaky-queue-test": "messaging",
    "debugging-plus-sign-email": "identity",
    "debugging-wrong-fee": "commerce",
    "diagrams-checkout-sequence": "commerce",
    "diagrams-password-reset": "identity",
    "diagrams-service-talk": "health",
    "diagrams-subscription-states": "saas",
    "maintainable-code-growing-function": "commerce",
    "maintainable-code-helpers-module": "saas",
    "maintainable-code-scaffold-docstrings": "iot",
    "maintainable-code-shape-of-a-diff": "saas",
    "naming-checkout-flag": "games",
    "naming-confirmed-column": "saas",
    "naming-misleading-function": "commerce",
    "naming-shipped-event": "iot",
    "plain-language-declined-card": "commerce",
    "plain-language-queue-runbook": "ops",
    "plain-language-release-notes": "saas",
    "plain-language-setup-guide": "ops",
    "resilience-duplicate-emails": "commerce",
    "resilience-inventory-service-down": "travel",
    "resilience-invoice-sync-job": "health",
    "resilience-refund-crash": "commerce",
    "secure-coding-api-key": "messaging",
    "secure-coding-convert-upload": "media",
    "secure-coding-file-download": "media",
    "secure-coding-search-sql": "saas",
}
# A skill that fits as well as the one under test also passes a `loads` case, because the case fails only when no fitting skill loads.
SIBLINGS = {
    "loads-accessible-ui-grey-contrast": ["mobile-apps"],
    "loads-accessible-ui-icon-delete": ["web-front-end"],
    "loads-accessible-ui-login-form": ["web-front-end", "mobile-apps"],
    "loads-accessible-ui-modal-keyboard": ["web-front-end"],
    "loads-debugging-flaky-queue-test": ["test-design"],
    "loads-diagrams-service-talk": ["system-design"],
    "loads-maintainable-code-helpers-module": ["modular-monolith"],
    "loads-plain-language-declined-card": ["technical-writing"],
    "loads-plain-language-queue-runbook": ["technical-writing", "incident-response"],
    "loads-plain-language-release-notes": ["technical-writing"],
    "loads-plain-language-setup-guide": ["technical-writing"],
    "loads-resilience-refund-crash": ["payments-and-finance"],
}
# The words of each skill's name, which a `loads` prompt must not use either.
NAME_WORDS = {
    "accessible-ui": ("accessib",),
    "debugging": ("debug",),
    "diagrams": ("diagram",),
    "maintainable-code": ("maintainab",),
    "naming": ("naming",),
    "plain-language": ("plain language", "plain-language"),
    "resilience": ("resilien",),
    "secure-coding": ("secure",),
}


class SkillTriggerCaseTests(unittest.TestCase):
    def test_the_first_three_picks_are_the_skills_the_most_roles_carry(self):
        carried = roles_carrying()
        by_count = [name for name, _ in carried.most_common() if name != "context"]
        self.assertEqual(sorted(by_count[:5]), ["diagrams", "maintainable-code", "naming", "plain-language", "secure-coding"])
        # accessible-ui ties for the next places at 4 roles, and is a judgment pick.
        self.assertEqual(carried["accessible-ui"], 4)
        self.assertEqual(max(carried[n] for n in carried if n not in SKILLS and n != "context"), 4)

    def test_each_skill_exists_and_the_triggers_come_from_its_description(self):
        for skill in SKILLS:
            with self.subTest(skill=skill):
                self.assertTrue((TEAM / "skills" / skill / "SKILL.md").is_file())
                text = description(skill)
                for word in TRIGGER_WORDS[skill]:
                    self.assertRegex(text, rf"\b{word}", f"{word} is not in the {skill} description")

    def test_each_skill_has_four_should_load_cases_and_four_near_misses(self):
        for skill in SKILLS:
            for prefix in ("loads", "skips"):
                with self.subTest(skill=skill, kind=prefix):
                    self.assertEqual(len(cases(prefix, skill)), 4)

    def test_a_should_load_case_needs_the_skill_and_a_near_miss_forbids_it(self):
        for skill in SKILLS:
            for case in cases("loads", skill) + cases("skips", skill):
                with self.subTest(case=case.name):
                    (grader,) = sorted((case / "graders").glob("*.md"))
                    data, _ = front_matter(grader)
                    self.assertEqual((data["type"], data["tool"]), ("tool_used", "Skill"))
                    for call in (f'{{"skill": "aidd-team:{skill}"}}', f'{{"skill":"{skill}"}}'):
                        self.assertRegex(call, data["input_match"])
                    self.assertNotRegex(f'{{"skill": "aidd-team:{skill}-other"}}', data["input_match"])
                    if case.name.startswith("loads"):
                        self.assertEqual((data["min"], data.get("max"), data.get("arm")), (1, None, None))
                    else:
                        self.assertEqual((data["min"], data["max"], data["arm"]), (0, 0, "both"))

    def test_a_near_miss_uses_the_descriptions_words_so_a_too_broad_description_would_fail_it(self):
        for skill in SKILLS:
            for case in cases("skips", skill):
                with self.subTest(case=case.name):
                    body = front_matter(case / "prompt.md")[1].lower()
                    self.assertTrue(any(re.search(rf"\b{word}", body) for word in TRIGGER_WORDS[skill]), body)

    def test_a_loads_prompt_describes_the_need_in_other_words_than_the_skills_description(self):
        """A prompt made of the description's words measures keyword routing, and a description tuned on it passes. So a `loads`
        prompt, and each held-out one, uses none of the trigger words and not the skill's name."""
        for case in sorted(EVALS.glob("loads-*")) + sorted(EVALS.glob("held-out-loads-*")):
            skill = next(s for s in SKILLS if case.name.split("loads-", 1)[1].startswith(s + "-"))
            body = prompt_of(case)
            with self.subTest(case=case.name):
                self.assertEqual([w for w in TRIGGER_WORDS[skill] if re.search(rf"\b{w}", body)], [])
                self.assertEqual([w for w in NAME_WORDS[skill] if w in body], [])

    def test_no_domain_holds_more_than_a_third_of_the_loads_prompts(self):
        loads = {c.name.removeprefix("loads-") for c in EVALS.glob("loads-*")}
        self.assertEqual(loads, set(DOMAIN), "list each loads case with its domain")
        for domain, count in Counter(DOMAIN.values()).items():
            self.assertLessEqual(count, len(DOMAIN) // 3, domain)

    def test_a_loads_case_accepts_a_sibling_skill_that_fits_and_nothing_else(self):
        for case in sorted(EVALS.glob("loads-*")):
            skill = next(s for s in SKILLS if case.name.removeprefix("loads-").startswith(s + "-"))
            (grader,) = sorted((case / "graders").glob("*.md"))
            data, _ = front_matter(grader)
            siblings = SIBLINGS.get(case.name, [])
            with self.subTest(case=case.name):
                for other in siblings:
                    self.assertRegex(f'{{"skill": "aidd-team:{other}"}}', data["input_match"])
                for nothing in ("context", f"{skill}-other", "aidd"):
                    self.assertNotRegex(f'{{"skill": "aidd-team:{nothing}"}}', data["input_match"])

    def test_each_skill_has_a_held_out_prompt_scored_apart(self):
        held = sorted(EVALS.glob("held-out-loads-*"))
        self.assertEqual(len(held), 8)
        self.assertEqual(sorted(next(s for s in SKILLS if c.name.removeprefix("held-out-loads-").startswith(s + "-")) for c in held), sorted(SKILLS))
        for case in held:
            data, _ = front_matter(case / "prompt.md")
            (grader,) = sorted((case / "graders").glob("*.md"))
            g, _ = front_matter(grader)
            with self.subTest(case=case.name):
                self.assertIn("held-out", data["tags"])
                self.assertEqual((g["type"], g["tool"], g["min"]), ("tool_used", "Skill", 1))
        for case in sorted(EVALS.glob("loads-*")) + sorted(EVALS.glob("skips-*")):
            self.assertNotIn("held-out", front_matter(case / "prompt.md")[0]["tags"], case.name)

    def test_a_trigger_prompt_loads_both_plugins_and_gives_no_way_to_write(self):
        for case in every_trigger():
            with self.subTest(case=case.name):
                data, body = front_matter(case / "prompt.md")
                self.assertEqual(data["plugins"], ["../..", "../../../.."])
                self.assertEqual(data["allowed_tools"], ["Read", "Glob", "Grep", "Skill"])
                self.assertIn("trigger", data["tags"])
                self.assertTrue(body.strip().startswith("This repository uses aidd. "))

    def test_prompts_are_distinct_and_name_no_aidd_internals(self):
        bodies = [front_matter(c / "prompt.md")[1] for c in every_trigger()]
        self.assertEqual(len(bodies), len(set(bodies)))
        for body in bodies:
            body = body.replace("This repository uses aidd.", "")
            for word in ("aidd", ".aidd", "schemas/", "AGENTS.md"):
                self.assertNotIn(word, body)


class GeneratedTriggerCaseTests(unittest.TestCase):
    """The trigger cases are written from triggers.json by plugins/aidd-team/evals/generate.py; a hand edit is stale."""

    @staticmethod
    def generator():
        import importlib.util
        import sys

        sys.dont_write_bytecode = True  # a __pycache__ folder in the evals folder would read as a case
        spec = importlib.util.spec_from_file_location("generate_trigger_cases", ROOT / "plugins" / "aidd-team" / "evals" / "generate.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_every_trigger_case_is_what_the_generator_writes(self):
        self.assertEqual(self.generator().main(["--check"]), 0, "run python3 plugins/aidd-team/evals/generate.py and commit the result")

    def test_check_names_a_hand_edited_case_and_the_generator_repairs_it(self):
        import contextlib
        import io
        import shutil
        import tempfile
        from pathlib import Path

        gen = self.generator()
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            shutil.copy(ROOT / "plugins" / "aidd-team" / "evals" / "triggers.json", folder / "triggers.json")
            with contextlib.redirect_stdout(io.StringIO()):
                gen.main([], folder=folder)
            case = folder / "loads-diagrams-password-reset" / "prompt.md"
            self.assertTrue(case.is_file())
            case.write_text(case.read_text(encoding="utf-8") + "extra\n", encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(gen.main(["--check"], folder=folder), 1)
                self.assertIn("stale: loads-diagrams-password-reset/prompt.md", out.getvalue())
                gen.main([], folder=folder)
            self.assertEqual(gen.main(["--check"], folder=folder), 0)


if __name__ == "__main__":
    unittest.main()
