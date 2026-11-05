"""An Intent traces its request: the `## Request coverage` table names, for each success criterion and hard constraint,
the slice that proves it, the work item that covers it, the question asked of the person, or the request's non-goal.
`aidd validate` checks each row. The tests read the kind of finding and a fragment, never a whole sentence."""

import os
import subprocess
import sys
import unittest
from unittest import mock

from helpers import ROOT, aidd_subprocess, hermetic_environ, run_cli, src_pythonpath
from test_intents import TWO_PHASES, RepoCase
from test_workitems import intent, spec

from aidd.workitems import intent_checks, validation

TABLE_HEAD = "| Request item | Covered by |\n| --- | --- |\n"
NO_REQUEST = "\n## Request coverage\n\nNo request: this Intent started from an idea.\n"


FIRST_SLICE = "\n## Phases\n\n### First slice\n\n- Acceptance:\n  - A1: The panel shows the status.\n  - A2: A missing status shows a message.\n- Order of work: the endpoint.\n"
OTHER_SLICES = "phases:\n  - id: P1\n    slices:\n      - {id: SPEC-7, title: b}\n"


def with_coverage(rows: str, extra: str = TWO_PHASES, first: str = FIRST_SLICE, iid: str = "INTENT-1") -> str:
    """A big Intent whose `### First slice` holds `first` and whose `## Request coverage` holds `rows`, one table line each."""
    return intent(iid, "g", extra) + first + f"\n## Request coverage\n\n{TABLE_HEAD}{rows}"


class CoverageTests(RepoCase):
    CASES = (
        # (what, the Intent's text, (errors or warnings, a fragment of the finding); None when clean)
        (
            "every row names a slice, a question, or a non-goal",
            with_coverage("| Export as CSV | SPEC-1 |\n| Audit log | deferred, asked: keep it for later? |\n| Mobile app | the request's non-goal |\n"),
            None,
        ),
        ("a row that names two slices", with_coverage("| Export as CSV | SPEC-1, SPEC-3 |\n"), None),
        ("a row with an empty cell", with_coverage("| Export as CSV |  |\n"), ("errors", "empty")),
        ("a row with no item", with_coverage("|  | SPEC-1 |\n"), ("errors", "empty")),
        ("a row that names the proof, an acceptance line", with_coverage("| Export as CSV | SPEC-1 A2 |\n"), None),
        ("a row that names a line of the first slice and a phase exit", with_coverage("| Export as CSV | SPEC-1 A1, exit: P1 |\n"), None),
        ("a row that names a later slice alone", with_coverage("| Export as CSV | SPEC-3 |\n"), None),
        ("a row that names a line of a later slice, written when it starts", with_coverage("| Export as CSV | SPEC-3 A4 |\n"), None),
        ("a line the first slice does not list", with_coverage("| Export as CSV | SPEC-1 A9 |\n"), ("errors", "no acceptance line")),
        ("a line when the first slice has no acceptance", with_coverage("| Export as CSV | SPEC-1 A1 |\n", first=""), ("errors", "no acceptance line")),
        ("a line of a slice the Intent does not list", with_coverage("| Export as CSV | SPEC-9 A1 |\n"), ("errors", "SPEC-9")),
        ("a phase the Intent does not list", with_coverage("| Export as CSV | exit: P9 |\n"), ("errors", "no phase")),
        ("a row that names none of the three", with_coverage("| Export as CSV | later |\n"), ("errors", "Export as CSV")),
        ("a slice the Intent does not list", with_coverage("| Export as CSV | SPEC-9 |\n"), ("errors", "SPEC-9")),
        ("deferred with no question", with_coverage("| Export as CSV | deferred, asked |\n"), ("errors", "question")),
        ("a row still holding a placeholder", with_coverage("| TODO: a success criterion | TODO |\n"), None),
        ("a big Intent with no section", intent("INTENT-1", "g", TWO_PHASES), ("warnings", "Request coverage")),
        ("a section that says there is no request", intent("INTENT-1", "g", TWO_PHASES) + NO_REQUEST, None),
        (
            "an Intent with one phase and no section",
            intent("INTENT-1", "g", "phases: [{id: P1, name: p, slices: [{id: SPEC-1, title: a}]}]\n"),
            ("warnings", "Request coverage"),
        ),
        ("a goal that is a minor fix, still open", with_coverage("| Fix the typo | minor fix |\n"), None),
        ("a minor fix that landed", with_coverage("| Fix the typo | merged_in 1a2b3c4 |\n"), None),
        ("a minor fix that landed, with a colon", with_coverage("| Fix the typo | merged_in: 1a2b3c4d5e6f |\n"), None),
        ("a landed minor fix with no commit", with_coverage("| Fix the typo | merged_in later |\n"), ("errors", "commit")),
        ("a landed minor fix with a short commit", with_coverage("| Fix the typo | merged_in 1a2b |\n"), ("errors", "commit")),
    )

    def clear(self, folder: str = "specs") -> None:
        for p in (self.root / folder).glob("*.md"):
            p.unlink()

    def coverage_findings(self, text: str) -> tuple[list[str], list[str]]:
        self.clear()
        self.write("specs/INTENT-1.md", text)
        errors, warnings = self.findings()
        return [e for e in errors if "INTENT-1" in e], [w for w in warnings if "overage" in w]

    def coverage_errors(self, files: dict[str, str]) -> tuple[list[str], list[str]]:
        """The Request coverage errors and warnings `aidd validate` gives for the repository's `files`."""
        self.clear()
        for rel, text in files.items():
            self.write(rel, text)
        errors, warnings = self.findings()
        return [e for e in errors if "overage" in e], [w for w in warnings if "overage" in w]

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

    def test_a_row_may_name_a_work_item_outside_this_intent(self):
        """A request can hold more than one goal: each gets its own Intent, or a Spec when one Spec does, so a row can
        name the work item that covers it, which must exist and must not be this Intent."""
        other = with_coverage("| Export as CSV | SPEC-7 |\n", extra=OTHER_SLICES, first="", iid="INTENT-2")
        for what, cell, kind in (
            ("an Intent that exists", "INTENT-2", None),
            ("an Intent that exists, with a slice", "SPEC-1, INTENT-2", None),
            ("a Spec outside this Intent that exists", "SPEC-20", None),
            ("an Intent that does not exist", "INTENT-9", "no work item"),
            ("a Spec that does not exist", "SPEC-21", "no work item"),
            ("this Intent itself", "INTENT-1", "this Intent itself"),
        ):
            with self.subTest(what):
                errors, _ = self.coverage_errors(
                    {
                        "specs/INTENT-1.md": with_coverage(f"| Export as CSV | {cell} |\n"),
                        "specs/INTENT-2.md": other,
                        "specs/SPEC-20.md": spec("SPEC-20", "draft"),
                    }
                )
                found = [e for e in errors if "INTENT-1" in e]
                if kind is None:
                    self.assertEqual(found, [], what)
                else:
                    self.assertTrue([e for e in found if cell in e and kind in e], (what, errors))

    def test_the_self_named_row_says_what_to_name_instead(self):
        errors, _ = self.coverage_errors({"specs/INTENT-1.md": with_coverage("| Export as CSV | INTENT-1 |\n")})
        self.assertTrue([e for e in errors if "name the work item that covers the item, or a slice of this one" in e], errors)

    def test_two_intents_that_name_each_other_cover_nothing(self):
        """The chain of Intent ids for one item must end at a slice, a phase, or a Spec, never come back to its start."""
        for what, two, three, kind in (
            ("they name each other", "INTENT-1", None, "back"),
            ("a chain of three comes back", "INTENT-3", "INTENT-1", "back"),
            ("the other Intent covers it with a slice", "SPEC-7", None, None),
            ("the chain ends at a slice", "INTENT-3", "SPEC-8", None),
            ("the other Intent defers it with a question", "deferred, asked: later?", None, None),
            ("the other Intent's row is a minor fix", "minor fix", None, None),
            ("the other Intent's minor fix landed", "merged_in 1a2b3c4", None, None),
        ):
            with self.subTest(what):
                files = {
                    "specs/INTENT-1.md": with_coverage("| Export as CSV | INTENT-2 |\n"),
                    "specs/INTENT-2.md": with_coverage(f"| Export as CSV | {two} |\n", extra=OTHER_SLICES, first="", iid="INTENT-2"),
                }
                if three:
                    slices = OTHER_SLICES.replace("SPEC-7", "SPEC-8")
                    files["specs/INTENT-3.md"] = with_coverage(f"| Export as CSV | {three} |\n", extra=slices, first="", iid="INTENT-3")
                errors, _ = self.coverage_errors(files)
                found = [e for e in errors if e.startswith("specs/INTENT-1.md") and "Export as CSV" in e]
                if kind is None:
                    self.assertEqual(found, [], (what, errors))
                else:
                    self.assertTrue([e for e in found if kind in e], (what, errors))

    def test_a_dense_set_of_intents_is_walked_once_each(self):
        """Repository text is another person's, so Intents whose rows each name all the others must not cost a walk of
        every path. The walk expands each Intent at most once for each Intent it starts from, counted, never timed."""
        ids = [f"INTENT-{n}" for n in range(1, 31)]
        objects = [(f"specs/{i}.md", {"type": "intent", "id": i, "status": "active"}) for i in ids]
        texts = {f"specs/{i}.md": f"\n## Request coverage\n\n{TABLE_HEAD}| Export as CSV | {', '.join(x for x in ids if x != i)} |\n" for i in ids}
        with mock.patch.object(intent_checks, "_row", wraps=intent_checks._row) as row:
            found = intent_checks.coverage_chain_findings(objects, texts)
        self.assertLessEqual(row.call_count, len(ids) * len(ids))
        self.assertEqual(len(found), len(ids), "each Intent's row comes back to it")
        self.assertTrue(all("and back to" in f for f in found), found)

    def test_a_long_chain_and_a_dense_set_cost_one_expansion_of_each_row(self):
        """One walk for each item, whatever the shape: each row is expanded once and each cell read a fixed few times, counted,
        never timed, and a long chain's finding names a few Intents and counts the rest."""
        chain = [f"INTENT-{n}" for n in range(1, 2001)]
        dense = [f"INTENT-{n}" for n in range(1, 401)]
        for what, ids, names in (
            ("a chain of 2,000 that comes back", chain, lambda i, k: chain[(k + 1) % len(chain)]),
            ("a dense 400, each naming the next 20", dense, lambda i, k: ", ".join(dense[(k + j) % len(dense)] for j in range(1, 21))),
        ):
            with self.subTest(what):
                objects = [(f"specs/{i}.md", {"type": "intent", "id": i, "status": "active"}) for i in ids]
                texts = {f"specs/{i}.md": f"\n## Request coverage\n\n{TABLE_HEAD}| Export as CSV | {names(i, k)} |\n" for k, i in enumerate(ids)}
                with (
                    mock.patch.object(intent_checks, "_row", wraps=intent_checks._row) as row,
                    mock.patch.object(intent_checks, "proofs_of", wraps=intent_checks.proofs_of) as cells,
                ):
                    found = intent_checks.coverage_chain_findings(objects, texts)
                self.assertLessEqual(row.call_count, len(ids))
                self.assertLessEqual(cells.call_count, 5 * len(ids))
                self.assertEqual(len(found), len(ids))
                self.assertLess(max(len(f) for f in found), 600, "a finding names a few Intents of a chain and counts the rest")

    def test_a_crafted_long_cell_is_one_error_and_never_backtracks(self):
        """Repository text is another person's, so a cell past the cap is one error before any pattern reads it. Each case
        runs in a child under a short timeout, so a pattern that backtracks fails the test instead of hanging the suite."""
        script = (
            "import sys; from aidd.workitems import intent_checks as c; cell = sys.stdin.read(); "
            "data = {'type': 'intent', 'id': 'INTENT-1', 'phases': [{'id': 'P1', 'slices': [{'id': 'SPEC-1'}]}]}; "
            "text = '## Request coverage\\n\\n| Item | Covered by |\\n| --- | --- |\\n| Export | ' + cell + ' |\\n'; "
            "print(c.coverage_findings('INTENT-1.md', text, data)); "
            "print(c.coverage_chain_findings([('INTENT-1.md', data)], {'INTENT-1.md': text}))"
        )
        for what, cell, long in (
            ("merged_in and a long run of colons", "merged_in" + ":" * 100_000 + " a b", True),
            ("merged_in and a long run of spaces and colons", "merged_in" + " :" * 50_000 + "x", True),
            ("a long proof", "SPEC-1 " + "a " * 50_000 + "A1", True),
            ("comments that never close", "<!--" * 60_000, False),
        ):
            with self.subTest(what):
                done = subprocess.run(
                    [sys.executable, "-c", script], input=cell, capture_output=True, text=True, timeout=20, env={**os.environ, "PYTHONPATH": src_pythonpath()}
                )
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(done.stdout.count(f"longer than {intent_checks.MAX_CELL}"), 1 if long else 0, done.stdout[:300])

    def test_a_row_naming_its_own_intent_is_one_error(self):
        errors, _ = self.coverage_errors({"specs/INTENT-1.md": with_coverage("| Export as CSV | INTENT-1 |\n")})
        self.assertEqual(len([e for e in errors if "Export as CSV" in e]), 1, errors)

    def test_a_row_naming_a_closed_spec_warns(self):
        for status in ("done", "cancelled"):
            with self.subTest(status):
                files = {"specs/INTENT-1.md": with_coverage("| Export as CSV | SPEC-20 |\n"), "specs/SPEC-20.md": spec("SPEC-20", status)}
                errors, warnings = self.coverage_errors(files)
                self.assertEqual([e for e in errors if "Export as CSV" in e], [])
                self.assertTrue([w for w in warnings if f"SPEC-20 is {status}" in w], warnings)

    def test_a_cell_names_at_most_the_capped_number_of_proofs(self):
        cell = ", ".join(f"SPEC-{n}" for n in range(1, intent_checks.MAX_PROOFS + 2))
        errors, _ = self.coverage_errors({"specs/INTENT-1.md": with_coverage(f"| Export as CSV | {cell} |\n")})
        self.assertTrue([e for e in errors if f"more than {intent_checks.MAX_PROOFS} proofs" in e], errors)

    def test_the_named_intent_must_hold_the_item(self):
        """Each Intent of one request covers the whole request, so the Intent a row names has a row for the item too."""
        files = {
            "specs/INTENT-1.md": with_coverage("| Export as CSV | INTENT-2 |\n"),
            "specs/INTENT-2.md": with_coverage("| Print it | SPEC-7 |\n", extra=OTHER_SLICES, first="", iid="INTENT-2"),
        }
        errors, _ = self.coverage_errors(files)
        self.assertTrue([e for e in errors if e.startswith("specs/INTENT-1.md") and "INTENT-2 has no row" in e], errors)

    def test_a_row_naming_a_closed_intent_warns(self):
        for status in ("cancelled", "done"):
            with self.subTest(status):
                closed = with_coverage("| Export as CSV | SPEC-7 |\n", extra=OTHER_SLICES, first="", iid="INTENT-2")
                closed = closed.replace("status: active", f"status: {status}")
                errors, warnings = self.coverage_errors({"specs/INTENT-1.md": with_coverage("| Export as CSV | INTENT-2 |\n"), "specs/INTENT-2.md": closed})
                self.assertEqual([e for e in errors if e.startswith("specs/INTENT-1.md")], [])
                self.assertTrue([w for w in warnings if f"INTENT-2 is {status}" in w and "non-goal" in w], warnings)

    def test_a_custom_specs_folder_holds_the_named_items(self):
        config = self.root / ".aidd" / "config.yaml"
        before = config.read_text(encoding="utf-8")
        self.addCleanup(config.write_text, before, encoding="utf-8")
        config.write_text(before + "specs_dir: work\n", encoding="utf-8")
        self.clear()
        self.write("work/INTENT-1.md", with_coverage("| Export as CSV | INTENT-2 |\n| Print it | SPEC-20 |\n"))
        self.write("work/INTENT-2.md", with_coverage("| Export as CSV | SPEC-7 |\n| Print it | SPEC-7 |\n", extra=OTHER_SLICES, first="", iid="INTENT-2"))
        self.write("work/SPEC-20.md", spec("SPEC-20", "draft"))
        errors, _ = self.findings()
        self.assertEqual([e for e in errors if "overage" in e], [])
        code, out = run_cli("validate", "work/INTENT-1.md")
        self.assertEqual(code, 0, out)
        self.write("work/INTENT-1.md", with_coverage("| Export as CSV | INTENT-9 |\n"))
        errors, _ = self.findings()
        self.assertTrue([e for e in errors if "INTENT-9" in e], errors)

    def test_the_in_intent_proofs_never_read_the_other_work_items(self):
        """A slice, a line of it, or a phase exit stands on the Intent alone, so the other work items are never read."""
        text = with_coverage("| Export as CSV | SPEC-1 A1 |\n| Print it | exit: P1 |\n| Audit | SPEC-3 |\n")
        data = {"type": "intent", "id": "INTENT-1", "phases": [{"id": "P1", "slices": [{"id": "SPEC-1"}, {"id": "SPEC-3"}]}]}
        lookup = mock.Mock(return_value={})
        self.assertEqual(intent_checks.coverage_findings("INTENT-1.md", text, data, lookup), [])
        lookup.assert_not_called()

    def test_the_repository_check_reads_the_work_items_once(self):
        files = {f"specs/INTENT-{n}.md": with_coverage(f"| Export as CSV | SPEC-{20 + n} |\n", iid=f"INTENT-{n}") for n in range(1, 4)}
        files.update({f"specs/SPEC-{20 + n}.md": spec(f"SPEC-{20 + n}", "draft") for n in range(1, 4)})
        self.clear()
        for rel, text in files.items():
            self.write(rel, text)
        with mock.patch.object(validation, "_work_items", wraps=validation._work_items) as read:
            errors, _ = self.findings()
        self.assertEqual([e for e in errors if "overage" in e], [])
        self.assertEqual(read.call_count, 1)

    @unittest.skipIf(sys.platform == "win32" or not os.path.exists("/dev/zero"), "a device file is needed")
    def test_a_link_to_a_device_never_hangs_validate(self):
        self.clear()
        self.write("specs/INTENT-1.md", with_coverage("| Export as CSV | INTENT-2 |\n"))
        os.symlink("/dev/zero", self.root / "specs" / "z.md")
        done = aidd_subprocess("validate", "specs/INTENT-1.md", cwd=self.root, env=hermetic_environ(), timeout=60)
        self.assertIn("INTENT-2", done.stdout + done.stderr)

    def test_validate_checks_the_named_intent_for_one_file(self):
        self.write("specs/INTENT-1.md", with_coverage("| Export as CSV | INTENT-9 |\n"))
        code, out = run_cli("validate", "specs/INTENT-1.md")
        self.assertNotEqual(code, 0, out)
        self.assertIn("INTENT-9", out)
        self.write("specs/INTENT-9.md", intent("INTENT-9", "g", "phases: [{id: P1, name: p, slices: [{id: SPEC-7, title: b}]}]\n"))
        code, out = run_cli("validate", "specs/INTENT-1.md")
        self.assertEqual(code, 0, out)
        self.assertNotIn("INTENT-9", out, out)

    def test_the_warning_names_the_next_step(self):
        _, warnings = self.coverage_findings(intent("INTENT-1", "g", TWO_PHASES))
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn("no request", warnings[0])

    def test_validate_shows_the_finding_for_one_file(self):
        self.write("specs/INTENT-1.md", with_coverage("| Export as CSV | SPEC-9 |\n"))
        code, out = run_cli("validate", "specs/INTENT-1.md")
        self.assertNotEqual(code, 0, out)
        self.assertIn("SPEC-9", out)

    def test_the_shipped_template_passes_its_own_check(self):
        text = (ROOT / ".agents" / "skills" / "aidd" / "assets" / "intent.md").read_text(encoding="utf-8")
        self.assertIn("## Request coverage", text)
        found = intent_checks.coverage_findings("INTENT-1.md", text, {"type": "intent", "phases": [{"slices": [{"id": "SPEC-TODO"}]}]})
        self.assertEqual([f for f in found if not f.startswith("warning: ")], [])


if __name__ == "__main__":
    unittest.main()
