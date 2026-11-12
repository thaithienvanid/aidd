"""Control tests for a target branch that moved since a branch forked from it.

Invariant: the base is the commit the branch forked from, so a run decides by the fork point's values, and it never fails a branch
because the target added a test since (that test may need code the branch lacks). But when the target's tip is ahead of the fork
point and what decides differs between the two, the run says so: one note with the next step, and `target_moved` in the evidence.
No note and no cost when the target has not moved, or moved without changing what decides.
"""

from __future__ import annotations

import unittest

from spec_repo_fixtures import FAIL, PASS, RepoCase, config_text, spec_text
from test_delegation_check import Case, codes

from aidd import testing
from aidd.kernel import git as kernel_git
from aidd.kernel import json_schema
from aidd.testing import target_view
from helpers import git

CONFIG = ".aidd/config.yaml"


class TargetMovedTests(RepoCase):
    def fork(self, main_files: dict[str, str], feat_files: dict[str, str] | None = None, landed: dict[str, str] | None = None) -> tuple[dict, list[str]]:
        """`landed` on main, then a branch `feat` from there with `feat_files`; main then moves with `main_files`; then `aidd test` on feat."""
        for path, text in (landed or {}).items():
            self.put(self.root, path, text)
        self.commit(self.root, "the fork point")
        self.branch("feat")
        for path, text in (feat_files or {"app/x.py": "x = 1\n"}).items():
            self.put(self.root, path, text)
        self.commit(self.root, "the change")
        git(self.root, "switch", "-q", "main")
        for path, text in main_files.items():
            self.put(self.root, path, text)
        self.commit(self.root, "main moves")
        git(self.root, "switch", "-q", "feat")
        return self.run_aidd()

    def moved_notes(self, notes: list[str]) -> list[str]:
        return [n for n in notes if "has moved since this branch forked" in n]

    def test_a_target_that_added_a_test_is_told_and_the_branch_is_not_failed_for_it(self):
        """The reviewer's case: `main` adds `guard` after the fork, and the branch's change would fail it. The run keeps the fork point's
        values (exit 0, results `unit`), records the move, and names the next step."""
        evidence, notes = self.fork({CONFIG: config_text(("unit", PASS, []), ("guard", FAIL, []))})
        self.assertEqual({n for n, _ in self.ran(evidence)}, {"unit"}, "the fork point's tests ran, as before")
        self.assertEqual(testing.exit_code(evidence), 0, "a target that moved is not a failure of the branch")
        tip = kernel_git.rev_parse("main", str(self.root))
        self.assertEqual(evidence["target_moved"]["tip"], tip)
        self.assertTrue(any("guard" in c for c in evidence["target_moved"]["changes"]), evidence["target_moved"])
        said = self.moved_notes(notes)
        self.assertEqual(len(said), 1, notes)
        self.assertIn("main", said[0])
        self.assertIn(tip[:12], said[0])
        self.assertIn("aidd test", said[0], "the note names the next step")

    def test_what_decides_in_the_config_and_what_does_not(self):
        base = ("unit", PASS, [])
        approvers = config_text(base).replace("approvers: [bob]", "approvers: [alice]")
        cases = {
            # (what main changes, whether the run says so)
            "a test added": ({CONFIG: config_text(base, ("guard", FAIL, []))}, True),
            "a test changed": ({CONFIG: config_text(("unit", FAIL, []))}, True),
            "a test removed": ({CONFIG: config_text()}, True),
            "a smoke marker set": ({CONFIG: config_text(base, smoke=("unit",))}, True),
            "specs_dir moved": ({CONFIG: config_text(base, extra="specs_dir: moved/\n")}, True),
            "docs_dir moved": ({CONFIG: config_text(base, extra="docs:\n  dir: elsewhere/\n")}, True),
            "the config removed": ({CONFIG: "not: [a config\n"}, True),
            "an owner changed": ({CONFIG: approvers}, False),
            "other files only": ({"README.md": "hello\n", "app/y.py": "y = 2\n"}, False),
            "nothing": ({}, False),
        }
        for name, (main_files, said) in cases.items():
            with self.subTest(main=name):
                self.fresh()
                evidence, notes = self.fork(main_files)
                self.assertEqual(bool(self.moved_notes(notes)), said, notes)
                self.assertEqual("target_moved" in evidence, said)
                self.assertEqual(testing.exit_code(evidence), 0, "the target's values never fail the branch")

    def test_the_state_of_a_spec_the_run_answers_to_counts_and_another_spec_does_not(self):
        approved = {"specs/SPEC-1.md": spec_text("SPEC-1", status="approved"), "specs/SPEC-2.md": spec_text("SPEC-2", status="approved")}
        own_edit = {"specs/SPEC-1.md": spec_text("SPEC-1", status="approved") + "\nA line the branch adds.\n"}
        cases = {
            # (what main changes, the changes the evidence names)
            "the Spec's status": ({"specs/SPEC-1.md": spec_text("SPEC-1", status="in_progress")}, ["SPEC-1: status"]),
            "the Spec's route": ({"specs/SPEC-1.md": spec_text("SPEC-1", status="approved", route="major")}, ["SPEC-1: route"]),
            "the Spec's command": ({"specs/SPEC-1.md": spec_text("SPEC-1", status="approved", code=FAIL)}, ["SPEC-1: test commands"]),
            "the Spec's scope": ({"specs/SPEC-1.md": spec_text("SPEC-1", status="approved", scope="lib/")}, ["SPEC-1: Task scope"]),
            "the Spec removed": ({"specs/SPEC-1.md": spec_text("SPEC-9", status="approved")}, ["SPEC-1 is gone"]),
            "another Spec the change does not hold": ({"specs/SPEC-2.md": spec_text("SPEC-2", status="in_progress")}, []),
            "the Spec's prose only": ({"specs/SPEC-1.md": spec_text("SPEC-1", status="approved") + "\nMore.\n"}, []),
        }
        for name, (main_files, named) in cases.items():
            with self.subTest(main=name):
                self.fresh()
                evidence, notes = self.fork(main_files, own_edit, approved)
                self.assertEqual(evidence.get("target_moved", {}).get("changes", []), named)
                self.assertEqual(bool(self.moved_notes(notes)), bool(named), notes)

    def test_what_the_evidence_holds_is_bounded_and_always_validates(self):
        """Each entry is at most the schema's 300 characters and there are at most the schema's `maxItems` of them: the first names and the
        count of the rest, a long value shortened. The run writes the evidence against its schema, so a breach raises; it is checked
        here too, and the note comes from the same entries."""
        limit = target_view.MAX_NAME
        most = json_schema.keyword_at(target_view.CHANGES, "maxItems")

        def tests(*names: str) -> str:
            return config_text(("unit", PASS, []), *((n, PASS, []) for n in names))

        specs = {f"specs/SPEC-{i}.md": spec_text(f"SPEC-{i}", status="approved") for i in range(1, 13)}
        in_progress = {f"specs/SPEC-{i}.md": spec_text(f"SPEC-{i}", status="in_progress") for i in range(1, 13)}
        cases = {
            # (what main changes, what the branch edits, what main landed first, whether an entry counts the rest)
            "one test": ({CONFIG: tests("a")}, None, None, False),
            "many tests": ({CONFIG: tests(*[f"t{i:02}" for i in range(30)])}, None, None, True),
            "a name at the limit": ({CONFIG: tests("n" * limit)}, None, None, False),
            "a name one past the limit": ({CONFIG: tests("n" * (limit + 1))}, None, None, False),
            "a very long name": ({CONFIG: tests("n" * 250)}, None, None, False),
            "a long folder": ({CONFIG: config_text(("unit", PASS, []), extra="specs_dir: " + "d" * 250 + "/\n")}, None, None, False),
            "more entries than the cap": ({**in_progress, CONFIG: tests("a", "b")}, {p: t + "\nMore.\n" for p, t in specs.items()}, specs, True),
        }
        for name, (main_files, feat_files, landed, counted) in cases.items():
            with self.subTest(main=name):
                self.fresh()
                evidence, notes = self.fork(main_files, feat_files, landed)
                found = evidence["target_moved"]["changes"]
                self.assertLessEqual(len(found), most)
                self.assertEqual(len(found) == most, name == "more entries than the cap")
                self.assertTrue(all(len(c) <= 300 for c in found), [len(c) for c in found])
                self.assertEqual(json_schema.validate(evidence, "evidence.schema.json"), [])
                self.assertEqual(any(" more" in c for c in found), counted, found)
                self.assertEqual(len(self.moved_notes(notes)), 1)

    def test_a_branch_that_holds_the_target_s_tip_is_not_told(self):
        """The fork point is the tip: nothing moved. The target's tip is read only when it is ahead of the fork point."""
        self.put(self.root, CONFIG, config_text(("unit", PASS, []), ("guard", PASS, [])))
        self.commit(self.root, "main adds a test")
        self.branch("feat")
        self.put(self.root, "app/x.py", "x = 1\n")
        self.commit(self.root, "the change")
        evidence, notes = self.run_aidd()
        self.assertEqual(({n for n, _ in self.ran(evidence)}, "target_moved" in evidence, self.moved_notes(notes)), ({"unit", "guard"}, False, []))

    def test_a_first_adoption_is_unchanged(self):
        """The fork point holds no config: the head's is all there is, and the target's later config is not compared with nothing."""
        (self.root / CONFIG).unlink()
        evidence, notes = self.fork({CONFIG: config_text(("unit", PASS, []), ("guard", FAIL, []))}, {CONFIG: config_text(("unit", PASS, []))})
        self.assertEqual(({n for n, _ in self.ran(evidence)}, "target_moved" in evidence, self.moved_notes(notes)), ({"unit"}, False, []))
        self.assertEqual(testing.exit_code(evidence), 0)

    def test_the_run_reads_the_local_ref_and_makes_no_network_call(self):
        """The tip is the ref `--base` resolved: with no remote at all the run still says it, and a fetch or a remote read would raise."""
        self.assertEqual(git(self.root, "remote"), "")
        evidence, _ = self.fork({CONFIG: config_text(("unit", PASS, []), ("guard", FAIL, []))})
        self.assertIn("target_moved", evidence)


class DelegatedMergeTests(Case):
    def test_a_delegated_merge_defers_on_a_head_that_does_not_hold_a_tip_that_added_a_test(self):
        """The same scenario as the first test, through the delegate's merge check: the tip changed what decides, the head does not
        hold it, and the check defers with `base_moved`, whose message names the tip."""
        repo = self.repo()
        head = repo.change(text="broken = True\n")
        text = (self.root / CONFIG).read_text(encoding="utf-8")
        repo.write(CONFIG, text.replace("tests:\n", 'tests:\n  - name: guard\n    command: [python3, -c, "raise SystemExit(1)"]\n', 1))
        tip = repo.commit("main adds a test the change would fail")
        result = repo.check(head)
        self.assertEqual(codes(result), ["base_moved"])
        self.assertIn(tip[:12], result["reasons"][0]["detail"])


if __name__ == "__main__":
    unittest.main()


class TheDelegateDefersOnAMovedTargetTests(unittest.TestCase):
    """A run that used the fork point's values does not hold the head to the target's newest tests, so neither the merge's
    suite check nor the Spec approval's red check takes it as proof. Both directions: evidence without the field is unchanged."""

    PASSED = {"results": [{"name": "unit", "red_green": "green", "status": "passed", "exit": 0}]}
    RED = {"results": [{"name": "check", "red_green": "red", "status": "failed", "exit": 1, "command": ["x"]}]}
    MOVED = {"target_moved": {"tip": "4e737924e4ca0000", "changes": ["`tests` added: guard"]}}

    def test_the_suite_check_and_the_red_check_defer_and_name_the_next_step(self):
        from aidd.delegation import local_run

        for decide, evidence in ((local_run.suite_problem, self.PASSED), (local_run.red_problem, self.RED)):
            with self.subTest(decide=decide.__name__):
                self.assertEqual(decide(evidence, ""), "")
                why = decide({**evidence, **self.MOVED}, "")
                self.assertIn("4e737924e4ca", why)
                self.assertIn("`tests` added: guard", why)
                self.assertIn("update the branch", why)
