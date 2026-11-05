"""An Intent traces its brief: the `## Brief coverage` table names, for each success criterion and hard constraint, the
slice that proves it, the question asked of the person, or the brief's non-goal. `aidd validate` checks each row.
The tests read the kind of finding and a fragment, never a whole sentence."""

import unittest

from helpers import ROOT, run_cli
from test_intents import TWO_PHASES, RepoCase
from test_workitems import intent

from aidd.workitems import intent_checks

TABLE_HEAD = "| Brief item | Covered by |\n| --- | --- |\n"
NO_BRIEF = "\n## Brief coverage\n\nNo brief: this Intent started from an idea.\n"


def with_coverage(rows: str, extra: str = TWO_PHASES) -> str:
    """A big Intent whose `## Brief coverage` holds `rows`, one table line each."""
    return intent("INTENT-1", "g", extra) + f"\n## Brief coverage\n\n{TABLE_HEAD}{rows}"


class CoverageTests(RepoCase):
    CASES = (
        # (what, the Intent's text, (errors or warnings, a fragment of the finding); None when clean)
        (
            "every row names a slice, a question, or a non-goal",
            with_coverage("| Export as CSV | SPEC-1 |\n| Audit log | deferred, asked: keep it for later? |\n| Mobile app | the brief's non-goal |\n"),
            None,
        ),
        ("a row that names two slices", with_coverage("| Export as CSV | SPEC-1, SPEC-3 |\n"), None),
        ("a row with an empty cell", with_coverage("| Export as CSV |  |\n"), ("errors", "empty")),
        ("a row with no item", with_coverage("|  | SPEC-1 |\n"), ("errors", "empty")),
        ("a row that names none of the three", with_coverage("| Export as CSV | later |\n"), ("errors", "Export as CSV")),
        ("a slice the Intent does not list", with_coverage("| Export as CSV | SPEC-9 |\n"), ("errors", "SPEC-9")),
        ("deferred with no question", with_coverage("| Export as CSV | deferred, asked |\n"), ("errors", "question")),
        ("a row still holding a placeholder", with_coverage("| TODO: a success criterion | TODO |\n"), None),
        ("a big Intent with no section", intent("INTENT-1", "g", TWO_PHASES), ("warnings", "Brief coverage")),
        ("a section that says there is no brief", intent("INTENT-1", "g", TWO_PHASES) + NO_BRIEF, None),
        ("an Intent with one phase and no section", intent("INTENT-1", "g", "slices: [{id: SPEC-1, title: a}]\n"), None),
    )

    def coverage_findings(self, text: str) -> tuple[list[str], list[str]]:
        for p in (self.root / "specs").glob("*.md"):
            p.unlink()
        self.write("specs/INTENT-1.md", text)
        errors, warnings = self.findings()
        return [e for e in errors if "INTENT-1" in e], [w for w in warnings if "overage" in w]

    def test_each_shape_of_coverage(self):
        for what, text, finding in self.CASES:
            with self.subTest(what):
                errors, warnings = self.coverage_findings(text)
                if finding is None:
                    self.assertEqual(errors + warnings, [], what)
                    continue
                kind, fragment = finding
                hits = [ln for ln in (errors if kind == "errors" else warnings) if fragment in ln]
                self.assertTrue(hits, (what, errors, warnings))
                if kind == "warnings":
                    self.assertEqual(errors, [], what)

    def test_the_warning_names_the_next_step(self):
        _, warnings = self.coverage_findings(intent("INTENT-1", "g", TWO_PHASES))
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn("no brief", warnings[0])

    def test_validate_shows_the_finding_for_one_file(self):
        self.write("specs/INTENT-1.md", with_coverage("| Export as CSV | SPEC-9 |\n"))
        code, out = run_cli("validate", "specs/INTENT-1.md")
        self.assertNotEqual(code, 0, out)
        self.assertIn("SPEC-9", out)

    def test_the_shipped_template_passes_its_own_check(self):
        text = (ROOT / ".agents" / "skills" / "aidd" / "assets" / "intent.md").read_text(encoding="utf-8")
        self.assertIn("## Brief coverage", text)
        found = intent_checks.coverage_findings("INTENT-1.md", text, {"type": "intent", "phases": [{"slices": [{"id": "SPEC-TODO"}]}]})
        self.assertEqual([f for f in found if not f.startswith("warning: ")], [])


if __name__ == "__main__":
    unittest.main()
