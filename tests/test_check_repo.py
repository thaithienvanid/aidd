"""`aidd validate` across Specs: what one Spec cannot see alone (ids, parents, overdue reviews, released outcomes)."""

import datetime as dt
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, git

from aidd.workitems import objects, validation
from aidd.setup import adoption

TODAY = dt.date(2026, 9, 28)
INC = (ROOT / "tests" / "fixtures" / "specs" / "INC-481.md").read_text(encoding="utf-8")  # backfill_due = "2026-09-24"
MAJOR = (ROOT / "tests" / "fixtures" / "specs" / "SPEC-223.md").read_text(encoding="utf-8")


class CheckRepoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template_dir = tempfile.TemporaryDirectory()
        cls.template = Path(cls.template_dir.name) / "repo"
        cls.template.mkdir()
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

    def test_a_backfill_due_that_is_not_a_date_is_an_error(self):
        self.write("INC-481.md", INC.replace('backfill_due: "2026-09-24"', "backfill_due: next tuesday"))
        errors, _ = self.findings()
        self.assertIn("specs/INC-481.md: emergency.backfill_due 'next tuesday' is not a date", errors)
        self.assertEqual(self.matching(errors, "post-incident review"), [])

    def test_a_parent_outside_the_repository_is_only_a_warning(self):
        self.write("INC-481.md", INC.replace("trace_id: inc-481", "trace_id: inc-481\nparent: INTENT-9", 1))
        errors, warnings = self.findings(today=dt.date(2026, 9, 23))
        self.assertEqual(
            self.matching(warnings, "parent INTENT-9"),
            ["specs/INC-481.md: parent INTENT-9 is not in specs/ (fine if the parent lives outside the repository)"],
        )
        self.assertEqual(self.matching(errors, "parent"), [])
        self.intent("INTENT-9", "phases: [{id: P1, name: p, slices: [{id: INC-481, title: Fix the outage}]}]\n")
        self.assertEqual(self.matching(self.findings(today=dt.date(2026, 9, 23))[1], "parent INTENT-9"), [])

    def intent(self, oid: str, extra: str = "") -> None:
        self.write(f"{oid}.md", f'---\ntype: intent\nid: "{oid}"\ntitle: "{oid}"\ngoal: Dealers track orders\n{extra}---\n')

    def test_a_parent_of_the_wrong_type_is_an_error_naming_the_type_found(self):
        """A Spec's parent is an Intent. A missing parent may live elsewhere (a warning); a parent that is here and of
        another type is wrong for certain (an error)."""
        self.intent("INTENT-1", "phases: [{id: P1, name: p, slices: [{id: INC-481, title: Fix the outage}]}]\n")
        self.write("INC-481.md", INC.replace("trace_id: inc-481", "trace_id: inc-481\nparent: INTENT-1", 1))
        errors, warnings = self.findings(today=dt.date(2026, 9, 23))
        self.assertEqual(self.matching(errors + warnings, "parent"), [], "Spec -> Intent, listed as its slice, is the shape")

        self.write("SPEC-223.md", MAJOR.replace("\ntitle:", "\nparent: INC-481\ntitle:", 1))
        errors, warnings = self.findings(today=dt.date(2026, 9, 23))
        self.assertEqual(self.matching(errors, "parent INC-481"), ["specs/SPEC-223.md: parent INC-481 is a Spec; a Spec's parent is an Intent"])
        self.assertEqual(self.matching(warnings, "parent INC-481"), [])

    def test_a_type_aidd_has_no_object_for_is_a_plain_error_naming_the_allowed_types(self):
        self.write("OLD-1.md", '---\naidd_version: "1.0.0"\ntype: epic\nid: OLD-1\ntitle: t\ngoal: g\n---\n')
        (error,) = validation.validate_file(self.root / "specs" / "OLD-1.md")
        self.assertIn("type must be spec, intent, proposal", error)

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

    def test_an_assisted_by_trailer_has_one_spelling_and_the_warning_gives_it(self):
        """On the branch's own commits, one warning per value with its commit count. A
        commit the default branch holds is left alone."""
        ident = ("-c", "user.name=T", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false")
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, *ident, "commit", "-q", "--allow-empty", "-m", "on main\n\nAssisted-by: Claude Code/old")
        git(self.root, "checkout", "-q", "-b", "feat")
        start = git(self.root, "rev-parse", "HEAD")
        cases = [
            ("claude-code/claude-opus-5-5", None),
            ("Claude Code/claude-opus-5-5", "claude-code/claude-opus-5-5"),
            ("claude/claude-opus-5-5", "claude-code/claude-opus-5-5"),  # well-formed, but not an id aidd knows
            ("some-tool/model-x", None),  # a harness aidd does not know keeps its own id
            ("codex", "codex/<model>"),
        ]
        for value, fix in cases:
            with self.subTest(value=value):
                git(self.root, "reset", "-q", start)
                for _ in range(2):
                    git(self.root, *ident, "commit", "-q", "--allow-empty", "-m", f"work\n\nAssisted-by: {value}")
                found = self.matching(self.findings()[1], "is not `<harness id>/<model>`")
                fixes = [re.search(r"write `(?:Assisted-by: )?([^`]*)`", w, re.I).group(1) for w in found]
                self.assertEqual(fixes, [fix] if fix else [], found)
                commits = [w for w in found if "of this branch" in w]
                self.assertEqual([("on 2 commits" in w, "git.push.force" in w) for w in commits], [(True, True)] if fix else [])


class ObjectTypeTests(unittest.TestCase):
    """aidd finds its objects by the front matter's top-level `type:`, and only for a type it knows: other tools write
    `type:` too."""

    def test_a_file_is_an_aidd_object_only_when_its_type_is_one_aidd_knows(self):
        cases = [
            ("type: spec\nid: SPEC-1\n", True, "spec"),
            ('type: "intent"\n', True, "intent"),
            ("type: intent  # a comment\n", True, "intent"),
            ("type: epic\n", False, ""),
            ("type: post\ntitle: A blog post\n", False, ""),
            ("title: no type at all\n", False, ""),
            ("  type: spec\n", False, ""),
            ("type: spec\n", True, "spec"),
        ]
        with tempfile.TemporaryDirectory() as d:
            for front, found, item_type in cases:
                with self.subTest(front=front):
                    p = Path(d) / "x.md"
                    p.write_text(f"---\n{front}---\n# Body\n", encoding="utf-8")
                    self.assertEqual((objects.is_object(p), objects.front_type(p)), (found, item_type))


if __name__ == "__main__":
    unittest.main()
