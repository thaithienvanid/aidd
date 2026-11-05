"""`aidd doctor` warns when a ruleset file requires only one of the `tests` and `ci passed` checks while a workflow of the
repository defines the other, and says what to add."""

import json
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, aidd_here

from aidd.setup import doctor_checks

CI = "name: ci\njobs:\n  ci-passed:\n    name: ci passed\n    runs-on: ubuntu-latest\n"
TESTS = "name: aidd-tests\njobs:\n  tests:\n    runs-on: ubuntu-latest\n"


def ruleset(*contexts: str, rule: str = "required_status_checks") -> str:
    checks = [{"context": c, "integration_id": 15368} for c in contexts]
    return json.dumps({"name": "main", "target": "branch", "rules": [{"type": "deletion"}, {"type": rule, "parameters": {"required_status_checks": checks}}]})


class RulesetCheckTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_a_ruleset_that_requires_only_tests_while_ci_passed_exists_warns_with_the_next_step(self):
        self.write(".github/workflows/ci.yml", CI)
        self.write(".github/workflows/aidd-tests.yml", TESTS)
        self.write(".github/rulesets/main.json", ruleset("tests"))
        [(level, message)] = doctor_checks.ruleset_checks(self.root)
        self.assertEqual(level, "warn")
        self.assertIn(".github/rulesets/main.json requires the `tests` check but not `ci passed`", message)
        self.assertIn("add it to required_status_checks in the file, then import the ruleset again", message)

    def test_a_ruleset_that_requires_only_ci_passed_while_tests_exists_warns(self):
        self.write(".github/workflows/ci.yml", CI)
        self.write(".github/workflows/aidd-tests.yml", TESTS)
        self.write(".github/rulesets/main.json", ruleset("ci passed"))
        [(level, message)] = doctor_checks.ruleset_checks(self.root)
        self.assertEqual(level, "warn")
        self.assertIn("requires the `ci passed` check but not `tests`", message)

    def test_a_ruleset_that_matches_what_the_repository_defines_is_quiet(self):
        self.write(".github/workflows/aidd-tests.yml", TESTS)
        self.write(".github/rulesets/main.json", ruleset("tests"))  # the template aidd writes, in a repository with only that workflow
        self.assertEqual(doctor_checks.ruleset_checks(self.root), [])
        self.write(".github/workflows/ci.yml", CI)
        self.write(".github/rulesets/main.json", ruleset("tests", "ci passed"))
        self.assertEqual(doctor_checks.ruleset_checks(self.root), [])
        self.write(".github/rulesets/main.json", ruleset())  # a ruleset that requires neither is another finding
        self.assertEqual(doctor_checks.ruleset_checks(self.root), [])

    def test_a_ruleset_that_is_not_about_status_checks_or_not_json_is_left_alone(self):
        self.write(".github/workflows/ci.yml", CI)
        self.write(".github/workflows/aidd-tests.yml", TESTS)
        self.write(".github/rulesets/tag.json", ruleset("tests", rule="creation"))
        self.write(".github/rulesets/broken.json", "{ not json")
        self.write(".github/rulesets/list.json", "[1, 2]")
        self.assertEqual(doctor_checks.ruleset_checks(self.root), [])

    def test_aidds_own_ruleset_and_the_template_it_writes_pass_their_own_check(self):
        self.assertEqual(doctor_checks.ruleset_checks(ROOT), [])
        self.write(".github/workflows/aidd-tests.yml", (ROOT / "templates" / "github" / "aidd-tests.yml").read_text(encoding="utf-8"))
        self.write(".github/rulesets/main.json", (ROOT / "templates" / "github" / "rulesets" / "main.json").read_text(encoding="utf-8"))
        self.assertEqual(doctor_checks.ruleset_checks(self.root), [])

    def test_doctor_prints_the_warning(self):
        self.write(".github/workflows/ci.yml", CI)
        self.write(".github/workflows/aidd-tests.yml", TESTS)
        self.write(".github/rulesets/main.json", ruleset("tests"))
        done = aidd_here("doctor", cwd=self.root)
        self.assertIn("requires the `tests` check but not `ci passed`", done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
