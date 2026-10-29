"""`aidd validate` across Specs: what one Spec cannot see alone (ids, parents, overdue reviews, released outcomes)."""

import datetime as dt
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd.workitems import validation
from aidd.setup import adoption

TODAY = dt.date(2026, 9, 28)
INC = (ROOT / "examples" / "_specs" / "INC-481.md").read_text(encoding="utf-8")  # review_due = "2026-09-24"
MAJOR = (ROOT / "examples" / "_specs" / "SPEC-223.md").read_text(encoding="utf-8")


class CheckRepoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template_dir = tempfile.TemporaryDirectory()
        cls.template = Path(cls.template_dir.name) / "repo"
        adoption.init(cls.template, adoption.InitOptions(profile="team", ci="none", links=[], skill=False, approvers=["@lead"], harnesses=[]))

    @classmethod
    def tearDownClass(cls):
        cls.template_dir.cleanup()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "repo"
        shutil.copytree(self.template, self.root, symlinks=True)

    def write(self, name, text):
        (self.root / "specs" / name).write_text(text, encoding="utf-8")

    def findings(self, today=TODAY):
        """(errors, warnings) with the repository path taken off, so each reads `specs/<file>: <message>`."""
        errors, warnings = validation.check_repo(self.root, today=today)
        strip = str(self.root) + "/"
        return [e.replace(strip, "") for e in errors], [w.replace(strip, "") for w in warnings]

    def matching(self, lines, needle):
        return [ln for ln in lines if needle in ln]

    def test_a_test_command_whose_program_is_a_variable_is_an_error_with_the_env_form(self):
        """A live run's `aidd init --test "PYTHONPATH=src python3 ..."` kept `PYTHONPATH=src` as the program, so no test
        could start. validate names the command and the `env` form that runs, in the config and in a Spec."""
        cfg = self.root / ".aidd" / "config.yaml"
        text = cfg.read_text(encoding="utf-8")
        cfg.write_text(text + "\ntests:\n  - name: unit\n    command: [PYTHONPATH=src, python3, -m, pytest]\n", encoding="utf-8")
        self.write("SPEC-223.md", MAJOR.replace("command: [pytest, -q, tests/test_user_timezone.py]", "command: [CI=1, pytest, -q]", 1))
        errors, _ = self.findings()
        self.assertEqual(
            self.matching(errors, "cannot start"),
            [
                ".aidd/config.yaml: the test command `unit` cannot start: `PYTHONPATH=src` is an environment variable, but aidd starts a "
                "command with no shell, so it would run `PYTHONPATH=src` as the program; start the command with `env`, as in "
                "`env PYTHONPATH=src python3 -m pytest`",
                "specs/SPEC-223.md: the test command `timezone` cannot start: `CI=1` is an environment variable, but aidd starts a "
                "command with no shell, so it would run `CI=1` as the program; start the command with `env`, as in `env CI=1 pytest -q`",
            ],
        )
        cfg.write_text(text, encoding="utf-8")
        self.write("SPEC-223.md", MAJOR.replace("command: [pytest, -q, tests/test_user_timezone.py]", "command: [env, CI=1, pytest, -q]", 1))
        self.assertEqual(self.matching(self.findings()[0], "cannot start"), [])

    def test_an_id_used_twice_is_an_error_naming_both_files(self):
        self.write("INC-481.md", INC)
        self.write("INC-481-copy.md", INC)
        errors, _ = self.findings()
        dupes = self.matching(errors, "is also used by")
        self.assertEqual(len(dupes), 1, errors)
        self.assertTrue(dupes[0].startswith("specs/INC-481.md: id INC-481"), dupes)  # object_files is sorted: INC-481-copy comes first
        self.assertTrue(dupes[0].endswith("specs/INC-481-copy.md"), dupes)

    def test_an_overdue_post_incident_review_needs_its_learn_ref(self):
        self.write("INC-481.md", INC)
        overdue = "specs/INC-481.md: post-incident review was due 2026-09-24; record outcome.learn_ref"
        self.assertIn(overdue, self.findings()[0])
        self.assertNotIn(overdue, self.findings(today=dt.date(2026, 9, 24))[0])  # due today is not overdue yet
        self.write("INC-481.md", INC.replace("\n---\n", "\n\noutcome:\n  learn_ref: docs/postmortems/inc-481.md\n---\n", 1))
        self.assertEqual(self.matching(self.findings()[0], "post-incident review"), [])

    def test_a_review_due_that_is_not_a_date_is_an_error(self):
        self.write("INC-481.md", INC.replace('review_due: "2026-09-24"', "review_due: next tuesday"))
        errors, _ = self.findings()
        self.assertIn("specs/INC-481.md: emergency.review_due 'next tuesday' is not a date", errors)
        self.assertEqual(self.matching(errors, "post-incident review"), [])

    def test_a_parent_outside_the_repository_is_only_a_warning(self):
        self.write("INC-481.md", INC.replace("trace_id: inc-481", "trace_id: inc-481\nparent: EPIC-9", 1))
        errors, warnings = self.findings(today=dt.date(2026, 9, 23))
        self.assertEqual(
            self.matching(warnings, "parent EPIC-9"), ["specs/INC-481.md: parent EPIC-9 is not in specs/ (fine if the parent lives outside the repository)"]
        )
        self.assertEqual(self.matching(errors, "parent"), [])
        epic = INC.replace("id: INC-481", "id: EPIC-9").replace("trace_id: inc-481", "trace_id: epic-9")
        self.write("EPIC-9.md", epic)
        self.assertEqual(self.matching(self.findings(today=dt.date(2026, 9, 23))[1], "parent EPIC-9"), [])

    def container(self, kind: str, oid: str, parent: str = "") -> None:
        link = f'parent: "{parent}"\n' if parent else ""
        self.write(f"{oid}.md", f'---\naidd_version: "1.0.0"\nkind: "{kind}"\nid: "{oid}"\n{link}title: "{oid}"\ngoal: Dealers track orders\n---\n')

    def test_a_parent_of_the_wrong_kind_is_an_error_naming_the_kind_found(self):
        """A Spec's parent is an Epic, and an Epic's parent is an Initiative. A missing parent may live elsewhere (a
        warning); a parent that is here and of another kind is wrong for certain (an error)."""
        self.container("initiative", "INIT-1")
        self.container("epic", "EPIC-1", parent="INIT-1")
        self.write("INC-481.md", INC.replace("trace_id: inc-481", "trace_id: inc-481\nparent: EPIC-1", 1))
        errors, warnings = self.findings(today=dt.date(2026, 9, 23))
        self.assertEqual(self.matching(errors + warnings, "parent"), [], "Spec -> Epic -> Initiative is the shape")

        self.write("INC-481.md", INC.replace("trace_id: inc-481", "trace_id: inc-481\nparent: INIT-1", 1))
        errors, warnings = self.findings(today=dt.date(2026, 9, 23))
        self.assertEqual(self.matching(errors, "parent"), ["specs/INC-481.md: parent INIT-1 is an Initiative; a Spec's parent is an Epic"])
        self.assertEqual(self.matching(warnings, "parent"), [])

        self.container("epic", "EPIC-2", parent="EPIC-1")
        self.container("epic", "EPIC-3", parent="INC-481")
        errors, _ = self.findings(today=dt.date(2026, 9, 23))
        self.assertIn("specs/EPIC-2.md: parent EPIC-1 is an Epic; an Epic's parent is an Initiative", errors)
        self.assertIn("specs/EPIC-3.md: parent INC-481 is a Spec; an Epic's parent is an Initiative", errors)

    def test_a_released_major_change_records_what_observe_found(self):
        released = MAJOR.replace("\n---\n", '\n\noutcome:\n  released_on: "2026-09-20"\n---\n', 1)
        self.write("SPEC-223.md", released)
        self.assertEqual(len(self.matching(self.findings()[1], "released major change has no outcome.observe_result")), 1)
        self.write("SPEC-223.md", released.replace('released_on: "2026-09-20"', 'released_on: "2026-09-20"\n  observe_result: pass'))
        self.assertEqual(self.matching(self.findings()[1], "observe_result"), [])
        self.write("SPEC-223.md", MAJOR)  # not released yet: nothing to record
        self.assertEqual(self.matching(self.findings()[1], "observe_result"), [])

    def test_observe_result_is_only_what_the_runner_records(self):
        # `aidd observe --write` records pass or fail; no command writes `skipped`, so the schema refuses it.
        released = MAJOR.replace("\n---\n", '\n\noutcome:\n  released_on: "2026-09-20"\n  observe_result: skipped\n---\n', 1)
        self.write("SPEC-223.md", released)
        self.assertTrue(self.matching(self.findings()[0], "observe_result"))
        self.write("SPEC-223.md", released.replace("observe_result: skipped", "observe_result: fail"))
        self.assertEqual(self.matching(self.findings()[0], "observe_result"), [])


if __name__ == "__main__":
    unittest.main()
