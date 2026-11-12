"""Trigger cases for ten practice skills, each with four should-load prompts and four near misses.

The picks follow `schemas/roles.json`: the skills the most distinct roles carry or preload, leaving out `context` (it fires at
the start of every step, so no request calls for it). The last pick is a judgment, and the README says so. `debugging` and `resilience` are findings: batch C3 saw neither load on seeded code. The cases are scored
by `tool_used: Skill` with the skill's name, with or without the `aidd-team:` prefix.
"""

import contextlib
import io
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from helpers import ROOT
from test_plugin_evals import TEAM_SUITE, front_matter, written_triggers

from aidd.evals import trigger_cases

TEAM = ROOT / "plugins" / "aidd-team"
SKILLS = (
    "accessible-ui",
    "cli-design",
    "data-model-design",
    "debugging",
    "diagrams",
    "maintainable-code",
    "naming",
    "plain-language",
    "resilience",
    "secure-coding",
)
# The words of each skill's description that name what calls for it. A near miss uses at least one of them and asks for no such task.
TRIGGER_WORDS = {
    "accessible-ui": ("screen", "form", "copy", "focus", "contrast"),
    "cli-design": ("flag", "prompt", "exit", "json", "color"),
    "data-model-design": ("schema", "config", "field", "enum"),
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
    return Counter(p for role in roles["roles"].values() for p in set(role.get("skills", [])) | set(role.get("preload", [])) - {"aidd"})


def description(skill: str) -> str:
    text = (TEAM / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
    return re.search(r'^description: "(.*)"$', text, re.M).group(1).lower()


def cases(prefix: str, skill: str):
    return sorted(written_triggers().glob(f"{prefix}-{skill}-*"))


def every_trigger():
    """The 80 development cases and the 10 held-out ones."""
    return sorted(written_triggers().glob("loads-*")) + sorted(written_triggers().glob("skips-*")) + sorted(written_triggers().glob("held-out-loads-*"))


def prompt_of(case) -> str:
    return front_matter(case / "prompt.md")[1].replace("This repository uses aidd.", "").lower()


# What a `loads` prompt asks for, by domain. No domain holds more than a third of them, so a description is not tuned to one kind of project.
DOMAIN = {
    "accessible-ui-grey-contrast": "mobile",
    "accessible-ui-icon-delete": "logistics",
    "accessible-ui-login-form": "identity",
    "accessible-ui-modal-keyboard": "saas",
    "cli-design-bulk-delete": "ops",
    "cli-design-machine-output": "analytics",
    "cli-design-option-clash": "media",
    "cli-design-status-numbers": "ci",
    "data-model-design-id-or-details": "iot",
    "data-model-design-layered-lists": "travel",
    "data-model-design-retry-settings": "messaging",
    "data-model-design-review-date": "health",
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
    "loads-data-model-design-id-or-details": ["schema-migration"],
    "loads-data-model-design-review-date": ["naming"],
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
    "cli-design": ("cli-design", "cli design"),
    "data-model-design": ("data-model", "data model"),
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
        # accessible-ui follows at 5 roles (the compliance analyst writes the accessibility statement), and is a judgment pick.
        self.assertEqual(carried["accessible-ui"], 5)
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
        for case in sorted(written_triggers().glob("loads-*")) + sorted(written_triggers().glob("held-out-loads-*")):
            skill = next(s for s in SKILLS if case.name.split("loads-", 1)[1].startswith(s + "-"))
            body = prompt_of(case)
            with self.subTest(case=case.name):
                self.assertEqual([w for w in TRIGGER_WORDS[skill] if re.search(rf"\b{w}", body)], [])
                self.assertEqual([w for w in NAME_WORDS[skill] if w in body], [])

    def test_no_domain_holds_more_than_a_third_of_the_loads_prompts(self):
        loads = {c.name.removeprefix("loads-") for c in written_triggers().glob("loads-*")}
        self.assertEqual(loads, set(DOMAIN), "list each loads case with its domain")
        for domain, count in Counter(DOMAIN.values()).items():
            self.assertLessEqual(count, len(DOMAIN) // 3, domain)

    def test_a_loads_case_accepts_a_sibling_skill_that_fits_and_nothing_else(self):
        for case in sorted(written_triggers().glob("loads-*")):
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
        held = sorted(written_triggers().glob("held-out-loads-*"))
        self.assertEqual(len(held), 10)
        self.assertEqual(sorted(next(s for s in SKILLS if c.name.removeprefix("held-out-loads-").startswith(s + "-")) for c in held), sorted(SKILLS))
        for case in held:
            data, _ = front_matter(case / "prompt.md")
            (grader,) = sorted((case / "graders").glob("*.md"))
            g, _ = front_matter(grader)
            with self.subTest(case=case.name):
                self.assertIn("held-out", data["tags"])
                self.assertEqual((g["type"], g["tool"], g["min"]), ("tool_used", "Skill", 1))
        for case in sorted(written_triggers().glob("loads-*")) + sorted(written_triggers().glob("skips-*")):
            self.assertNotIn("held-out", front_matter(case / "prompt.md")[0]["tags"], case.name)

    def test_a_trigger_prompt_loads_both_plugins_and_gives_no_way_to_write(self):
        for case in every_trigger():
            with self.subTest(case=case.name):
                data, body = front_matter(case / "prompt.md")
                self.assertEqual(data["plugins"], ["../../../plugins/aidd-team", "../../.."])
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


class WrittenTriggerCaseTests(unittest.TestCase):
    """`aidd.evals.trigger_cases` writes the trigger cases from triggers.json before a run, and no commit holds them, so a
    hand edit cannot drift from triggers.json and an install never carries them."""

    def tree(self, folder: Path) -> dict[str, bytes]:
        return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}

    def test_the_same_triggers_json_writes_the_same_cases_every_time(self):
        data = trigger_cases.load_triggers(ROOT)
        self.assertEqual(trigger_cases.case_files(data), trigger_cases.case_files(json.loads(json.dumps(data))))
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            first, second = Path(a), Path(b)
            self.assertEqual(len(trigger_cases.write_cases(first, data)), 4 * 90)
            trigger_cases.write_cases(second, data)
            self.assertEqual(self.tree(first), self.tree(second))
            self.assertEqual(self.tree(first), self.tree(written_triggers()))
            self.assertEqual(trigger_cases.write_cases(first, data), [], "a second write changes nothing")

    def test_a_write_repairs_a_hand_edit_and_removes_a_case_triggers_json_dropped(self):
        data = trigger_cases.load_triggers(ROOT)
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            trigger_cases.write_cases(folder, data)
            case = folder / "loads-diagrams-password-reset" / "prompt.md"
            case.write_text(case.read_text(encoding="utf-8") + "extra\n", encoding="utf-8")
            (folder / "loads-diagrams-gone").mkdir()
            (folder / "flow-kept-by-hand").mkdir()
            changed = trigger_cases.write_cases(folder, data)
            self.assertEqual(changed, ["removed: loads-diagrams-gone (not in triggers.json)", "wrote: loads-diagrams-password-reset/prompt.md"])
            self.assertEqual(self.tree(folder), self.tree(written_triggers()))
            self.assertTrue((folder / "flow-kept-by-hand").is_dir(), "a case by hand is never removed")

    def test_the_module_writes_into_the_suite_of_the_checkout_it_is_given(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            out = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(out):
                self.assertEqual(trigger_cases.main([str(root)]), 2)
            self.assertIn("no evals/team/triggers.json", out.getvalue())
            (root / "evals" / "team").mkdir(parents=True)
            shutil.copy(ROOT / trigger_cases.TRIGGERS_FILE, root / trigger_cases.TRIGGERS_FILE)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(trigger_cases.main([str(root)]), 0)
            written = {p.name for p in (root / "evals" / "team").iterdir() if p.is_dir()}
            self.assertEqual(written, {p.name for p in written_triggers().iterdir()})

    def test_no_commit_holds_a_written_case_and_no_case_by_hand_looks_like_one(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        written = {rel.split("/", 1)[0] for rel in trigger_cases.case_files(trigger_cases.load_triggers(ROOT))}
        for prefix in trigger_cases.PREFIXES:
            self.assertIn(f"evals/team/{prefix}*/", ignored, prefix)
        self.assertEqual([p.name for p in TEAM_SUITE.iterdir() if p.is_dir() and p.name.startswith(trigger_cases.PREFIXES) and p.name not in written], [])
        if (ROOT / ".git").exists():
            tracked = subprocess.run(["git", "ls-files", "evals/team"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
            self.assertEqual([t for t in tracked if t.split("/")[2].startswith(trigger_cases.PREFIXES)], [])


if __name__ == "__main__":
    unittest.main()
