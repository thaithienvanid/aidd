"""The loop's design as table-driven cases (tests/graph_cases.py): every row of its transition table, its deploy shapes, its
stored words, and its hard cases is one row of data in tests/fixtures/design/graph_cases/, and each case of a row is read by the
reader of the package that makes it pass.

Today's code does not hold the new model, so most cases wait on a package: they run against the current code and are expected
failures, shown as such in the run, and the suite stays green. A case the current code already reads right runs for real. When
a package lands, its reader goes in `READERS`; its cases then run for real, and a case that was expected to fail and passes fails
the run until its package is added.
"""

import io
import json
import re
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts src on sys.path)

import data_rules as dr
import graph_cases as lc
import graph_repo

TABLES = {table: lc.load(table) for table in lc.TABLES}
ALL_CASES = [case for rows in TABLES.values() for row in rows for case in lc.cases_of(row)]


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")[:40]


def case_test(case: lc.Case, part: str, readers: dict, current=lc.read_current, switched: dict | None = None):
    """One part of one case as a test: it passes when the case's reader reads what the design says, and a case whose package has
    no reader yet, and that no Task switched on, is an expected failure, run against `current`, the reader of the code as it is."""
    switched = lc.SWITCHED_ON if switched is None else switched

    def test(self):
        self.assertEqual(lc.run_case(case, part, readers, current, switched), [], f"{case.label} {part}")

    test.__name__ = f"test_{case.row.replace('-', '_')}{'_' + slug(case.name) if case.name else ''}_{part}"
    return test if lc.reader_for(case, part, readers, switched) else unittest.expectedFailure(test)


def run(test_fn) -> unittest.TestResult:
    """Run one generated test on its own, as the suite would, and give its result."""
    case = type("OneCase", (unittest.TestCase,), {test_fn.__name__: test_fn})(test_fn.__name__)
    return unittest.TextTestRunner(stream=io.StringIO()).run(unittest.TestSuite([case]))


class Cases(unittest.TestCase):
    """Every part of every case, one test each. The name says the row, the variant, and the part."""


for _case in ALL_CASES:
    for _part in lc.parts_of(_case):
        _test = case_test(_case, _part, lc.READERS)
        setattr(Cases, _test.__name__, _test)


def compatible(one, two) -> bool:
    """Whether two expected values can both be right: equal, or one is a list that holds the other."""
    a, b = (x if isinstance(x, list) else [x] for x in (one, two))
    return one == two or bool(set(map(json.dumps, a)) & set(map(json.dumps, b)))


def conflicts(cases: list[lc.Case]) -> list[str]:
    """Two cases that hold equal facts must not read different things: no reader could pass both."""
    seen: dict[str, lc.Case] = {}
    out = []
    for case in cases:
        key = json.dumps(case.facts, sort_keys=True)
        other = seen.setdefault(key, case)
        if other is not case:
            out += [
                f"{other.label} and {case.label} hold equal facts and read {k} differently"
                for k in set(other.reads) & set(case.reads)
                if not compatible(other.reads[k], case.reads[k])
            ]
    return out


class Tables(unittest.TestCase):
    def test_each_table_has_as_many_rows_as_the_design_names_and_each_case_names_its_package_and_read(self):
        for table, rows in TABLES.items():
            self.assertEqual(lc.count_problems(table, rows), [], table)

    def test_the_counts_are_the_designs(self):
        self.assertEqual({t: len(rows) for t, rows in TABLES.items()}, {"transitions": 35, "deploy-shapes": 24, "stored-words": 7, "hard-cases": 34})

    def test_each_table_names_the_design_and_the_table_it_was_made_from(self):
        for table, (name, label, _) in lc.TABLES.items():
            head = json.loads((lc.CASES / name).read_text(encoding="utf-8"))
            self.assertEqual(head["design"], lc.DESIGN, table)
            self.assertTrue(head["table"].startswith(label.split(",")[0]), table)

    def test_every_id_is_unique_across_the_tables_and_names_its_row(self):
        ids = [row["id"] for rows in TABLES.values() for row in rows]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual([r["id"] for r in TABLES["transitions"]], [*(f"T{n}" for n in range(1, 19)), "T18a", *(f"T{n}" for n in range(19, 35))])
        self.assertEqual([r["id"] for r in TABLES["deploy-shapes"]], [f"C1-{n:02d}" for n in range(1, 25)])
        self.assertEqual([r["id"] for r in TABLES["stored-words"]], [f"C2-W{n}" for n in range(1, 8)])
        self.assertEqual([r["id"] for r in TABLES["hard-cases"]], [f"C2-H{n:02d}" for n in range(1, 35)])

    def test_every_package_a_case_names_is_one_of_the_redesign_in_landing_order(self):
        self.assertEqual(list(lc.PACKAGES), list(dr.packages())[: len(lc.PACKAGES)])
        for case in ALL_CASES:
            for part in lc.parts_of(case):
                self.assertIn(lc.package_of(case, part), lc.PACKAGES, case.label)

    def test_the_facts_and_the_reads_use_only_the_keys_the_design_of_the_files_gives(self):
        for case in ALL_CASES:
            self.assertLessEqual(set(case.facts), lc.FACT_KEYS, case.label)
            self.assertLessEqual(set(case.reads), {*lc.STATUS_KEYS, *lc.NEXT_KEYS}, case.label)

    def test_what_only_a_person_knows_is_told_and_marked(self):
        for case in ALL_CASES:
            self.assertEqual("told" in case.facts, case.needs_person, f"{case.label}: `told` and `needs_person` go together")

    def test_a_reader_of_files_never_sees_the_saying(self):
        for case in ALL_CASES:
            if "told" in case.facts:
                self.assertTrue(all(isinstance(s, str) and s for s in case.facts["told"]), case.label)

    def test_a_pre_merge_built_case_has_an_approval_that_holds_and_every_task_ticked(self):
        for case in ALL_CASES:
            specs = {**({"SPEC-1": case.facts["spec"]} if case.facts.get("spec") else {}), **(case.facts.get("specs") or {})}
            for spec_id, spec in specs.items():
                if spec.get("status") not in ("approved", "in_progress", "built") or case.facts.get("trunk") or spec.get("route") == "emergency":
                    continue
                broken = case.row in ("T10", "T18a", "C2-H08", "C2-H22", "C2-H25", "C2-H21")
                if not broken:
                    self.assertTrue(spec.get("approval"), f"{case.label}: {spec_id} reads {spec['status']} and holds no approval")
                if spec["status"] == "built" and not broken:
                    self.assertTrue(all(t.get("done") for t in spec.get("tasks", [])), f"{case.label}: {spec_id} reads built with a Task not ticked")

    def test_no_two_cases_with_equal_facts_read_different_things(self):
        self.assertEqual(conflicts(ALL_CASES), [])

    def test_two_cases_with_equal_facts_and_different_reads_fail(self):
        one = lc.Case("X1", "", {"spec": {"status": "built"}}, {"status": "built"}, "C4", None, False)
        two = lc.Case("X2", "", {"spec": {"status": "built"}}, {"status": "ready"}, "C4", None, False)
        self.assertTrue(conflicts([one, two]))
        self.assertEqual(conflicts([one, lc.Case("X3", "", {"spec": {"status": "built"}}, {"status": "built", "line": "S12"}, "C4", "C5", False)]), [])

    def test_the_two_cases_the_review_found_no_longer_conflict(self):
        rows = {r["id"]: r for table in TABLES.values() for r in table}
        built = lc.cases_of(rows["T13"])[0].facts
        chain = next(c for c in lc.cases_of(rows["C2-H08"]) if "no approval" in c.name)
        self.assertNotEqual(built, chain.facts)

    def test_deleting_one_row_fails_the_count(self):
        for table, rows in TABLES.items():
            found = lc.count_problems(table, rows[1:])
            self.assertEqual(len(found), 1, table)
            self.assertIn("rows, and the design has", found[0], table)

    def test_a_repeated_id_a_missing_package_a_lone_variant_and_a_case_that_reads_nothing_fail(self):
        rows = TABLES["stored-words"]
        text = lambda changed: " ".join(lc.count_problems("stored-words", [*rows[:6], changed]))  # noqa: E731
        self.assertIn("used twice", " ".join(lc.count_problems("stored-words", [*rows[:6], dict(rows[0])])))
        self.assertIn("status_package", text(dict(rows[6], status_package="C9")))
        self.assertIn("says nothing", text(dict(rows[6], reads={})))
        self.assertIn("fewer than two", text(dict(rows[6], variants=[{"name": "a", "facts": rows[6]["facts"], "reads": rows[6]["reads"]}])))


def a_case(**reads) -> lc.Case:
    return lc.cases_of(
        {"id": "X1", "title": "a case of the proofs", "status_package": "C4", "next_package": "C4", "facts": {"spec": {"status": "built"}}, "reads": reads}
    )[0]


def reader_of(**reads):
    """A reader that reads the same whatever the facts, for a proof of the mechanism that must not depend on the current code."""
    return lambda facts: dict(reads)


class Mechanism(unittest.TestCase):
    """What lets a builder switch a package on, and what stops a package from being forgotten. The cases here are made for the
    proof, and the readers are fakes, so a package that lands never changes what these tests show."""

    case = a_case(status="built", acts="agent", action=None, line="S12")
    right = staticmethod(reader_of(status="built", acts="agent", action=None, line="S12"))
    wrong = staticmethod(reader_of(status="draft", acts="person", action=None, line="S8"))
    no_line = staticmethod(reader_of(status="built", acts="agent", action=None))

    def test_a_case_whose_package_has_no_reader_is_an_expected_failure_and_the_suite_stays_green(self):
        result = run(case_test(self.case, "status", {}, current=self.wrong))
        self.assertTrue(result.wasSuccessful())
        self.assertEqual((len(result.expectedFailures), len(result.unexpectedSuccesses)), (1, 0))

    def test_a_case_expected_to_fail_that_passes_fails_the_run(self):
        result = run(case_test(self.case, "status", {}, current=self.right))
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(len(result.unexpectedSuccesses), 1)

    def test_pointing_a_package_at_its_reader_runs_its_cases_for_real(self):
        for part in ("status", "next"):
            result = run(case_test(self.case, part, {"C4": self.right}))
            self.assertEqual((result.wasSuccessful(), result.expectedFailures, result.unexpectedSuccesses, result.failures), (True, [], [], []), part)

    def test_a_case_of_a_landed_package_that_reads_wrong_is_a_real_failure(self):
        for part in ("status", "next"):
            result = run(case_test(self.case, part, {"C4": self.wrong}))
            self.assertEqual((result.wasSuccessful(), len(result.failures)), (False, 1), part)

    def test_a_reader_of_a_landed_package_gives_the_line_and_a_wrong_line_fails(self):
        self.assertEqual(lc.run_case(self.case, "next", {"C4": self.right}), [])
        self.assertTrue(lc.run_case(self.case, "next", {"C4": self.no_line}), "no line fails")
        self.assertTrue(lc.run_case(self.case, "next", {"C4": reader_of(acts="agent", action=None, line="S99")}), "a wrong line fails")
        self.assertTrue(lc.problems({"line": "S12", "acts": "agent", "action": None}, {"acts": "agent", "action": None}, "next"))

    def test_only_the_current_code_may_leave_the_line_out(self):
        self.assertEqual(lc.problems({"line": "S12", "acts": "agent"}, {"acts": "agent"}, "next", relaxed=True), [])
        self.assertTrue(lc.problems({"line": "S12", "acts": "agent"}, {"acts": "agent", "line": "S8"}, "next", relaxed=True), "a wrong line still fails")
        self.assertTrue(lc.problems({"item_lines": {"SPEC-1": {"line": "S3"}}}, {"acts": "agent"}, "next"))
        self.assertEqual(lc.problems({"item_lines": {"SPEC-1": {"line": "S3"}}}, {"acts": "agent"}, "next", relaxed=True), [])

    def test_a_broken_expected_value_of_a_case_that_runs_fails(self):
        for key, value in (("status", "approved"), ("acts", "person"), ("action", "pr.merge")):
            case = a_case(**{"status": "built", "acts": "agent", "action": None, "line": "S12", key: value})
            result = run(case_test(case, "next" if key != "status" else "status", {"C4": self.right}))
            self.assertEqual(len(result.failures), 1, key)

    def test_a_part_a_task_switched_on_runs_for_real_and_the_rest_of_its_package_still_waits(self):
        switched = {(self.case.label, "status"): self.right}
        result = run(case_test(self.case, "status", {}, current=self.wrong, switched=switched))
        self.assertEqual((result.wasSuccessful(), result.expectedFailures, result.unexpectedSuccesses), (True, [], []))
        wrong = run(case_test(self.case, "status", {}, current=self.right, switched={(self.case.label, "status"): self.wrong}))
        self.assertEqual((wrong.wasSuccessful(), len(wrong.failures)), (False, 1), "a switched part that reads wrong is a real failure")
        waits = run(case_test(self.case, "next", {}, current=self.wrong, switched=switched))
        self.assertEqual((waits.wasSuccessful(), len(waits.expectedFailures)), (True, 1), "the other part of the case still waits")

    def test_each_switched_part_names_a_case_and_a_part_that_exist_and_waits_on_a_package_with_no_reader(self):
        parts = {(c.label, part): c for c in ALL_CASES for part in lc.parts_of(c)}
        for key in lc.SWITCHED_ON:
            with self.subTest(key=key):
                self.assertIn(key, parts)
                self.assertNotIn(lc.package_of(parts[key], key[1]), lc.READERS, "a landed package reads it: drop the entry")

    def test_a_finding_is_matched_by_its_whole_phrase_or_its_level_and_never_by_a_word(self):
        phrase = "its approval has no hold: the squash merge dropped its trailer. Run aidd approve INTENT-2"
        self.assertEqual(lc.problems({"findings": [phrase]}, {"findings": [phrase]}, "status"), [])
        self.assertTrue(lc.problems({"findings": [phrase]}, {"findings": ["approval"]}, "status"), "one word is no finding")
        self.assertTrue(lc.problems({"findings": [phrase]}, {"findings": [phrase + " now"]}, "status"), "a longer sentence is not it")
        self.assertEqual(lc.problems({"findings": [{"level": "error"}]}, {"findings": [{"level": "error", "text": "x"}]}, "status"), [])
        self.assertTrue(lc.problems({"findings": [{"level": "error"}]}, {"findings": [{"level": "warning", "text": "x"}]}, "status"))
        self.assertTrue(lc.problems({"findings": ["a"]}, {"status": "built"}, "status"), "a finding is read, or the case fails")

    def test_other_expected_values(self):
        self.assertTrue(lc.problems({"status": "built"}, None, "status"), "facts the reader cannot hold fail")
        self.assertEqual(lc.problems({"status": ["merged", "done"]}, {"status": "done"}, "status"), [])
        self.assertEqual(lc.problems({"statuses": {"A": "done"}}, {"statuses": {"A": "done", "B": "x"}}, "status"), [])
        self.assertTrue(lc.problems({"statuses": {"A": "done"}}, {"statuses": {"A": "draft"}}, "status"))
        self.assertTrue(lc.problems({"criteria": {"S1": {"measure_from": "2026-12-18"}}}, {"criteria": {"S1": {"measure_from": "2026-12-19"}}}, "status"))

    def test_each_waiting_case_fails_by_a_mismatch_and_never_by_an_error(self):
        for case in ALL_CASES:
            for part in lc.parts_of(case):
                if not lc.reader_for(case, part, lc.READERS, lc.SWITCHED_ON):
                    self.assertTrue(lc.run_case(case, part, lc.READERS), f"{case.label} {part} reads right already: add its package to READERS")

    def test_the_cases_the_current_code_reads_right_are_real_tests_and_not_expected_failures(self):
        today = [(c, part) for c in ALL_CASES for part in lc.parts_of(c) if lc.package_of(c, part) == "today"]
        self.assertTrue(today, "some cases already read right")
        for case, part in today:
            test = getattr(Cases, case_test(case, part, lc.READERS).__name__)
            self.assertFalse(getattr(test, "__unittest_expecting_failure__", False), case.label)


class Builder(unittest.TestCase):
    """The one builder every reader starts from makes the files and the repository of a case, whatever facts it holds."""

    @staticmethod
    def build(facts: dict) -> graph_repo.Built:
        tmp = tempfile.TemporaryDirectory()
        Builder.keep.append(tmp)
        return graph_repo.build(facts, Path(tmp.name).resolve() / "repo")

    keep: list = []

    @classmethod
    def tearDownClass(cls):
        for tmp in cls.keep:
            tmp.cleanup()

    def test_every_shape_of_facts_in_the_tables_builds(self):
        seen = set()
        for case in ALL_CASES:
            shape = frozenset(case.facts)
            if shape in seen:
                continue
            seen.add(shape)
            built = self.build(case.facts)
            self.assertTrue((built.root / ".git").exists(), case.label)

    def test_commits_carry_their_trailers_and_what_they_change_and_a_name_stands_for_its_id(self):
        facts = {
            "spec": {"status": "built", "reviews": [{"type": "code", "commit": "b7d20f4", "open": 0}]},
            "git": {
                "commits": [
                    {
                        "name": "b7d20f4",
                        "on": "feat",
                        "trailers": {"Approved-by": "Mai <mai@example.com>", "Approves": "INTENT-1"},
                        "changes": ["src/checkout/discount.py"],
                    }
                ]
            },
        }
        built = self.build(facts)
        message = graph_repo.helpers.git(built.root, "log", "-1", "--format=%B", built.shas["b7d20f4"])
        self.assertIn("Approved-by: Mai <mai@example.com>\nApproves: INTENT-1", message)
        self.assertIn("src/checkout/discount.py", graph_repo.helpers.git(built.root, "show", "--name-only", "--format=", built.shas["b7d20f4"]))
        self.assertIn(built.shas["b7d20f4"], (built.root / "specs" / "SPEC-1.md").read_text(encoding="utf-8"))

    def test_releases_are_written_in_the_order_given_and_a_history_holds_the_specs_it_names(self):
        rows = {r["id"]: r for table in TABLES.values() for r in table}
        facts = lc.cases_of(rows["C1-21"])[0].facts
        released = [r["released_at"] for r in facts["releases"]]
        self.assertNotEqual(released, sorted(released), "the case lists its releases out of time order")
        built = self.build(facts)
        names = sorted(p.name for p in (built.root / "docs" / "releases").iterdir())
        self.assertEqual(names, ["production-2026-11-20-1.md", "production-2026-11-20-2.md"])
        tip = graph_repo.helpers.git(built.root, "ls-tree", "-r", "--name-only", "main")
        self.assertIn("specs/SPEC-1.md", tip)
        older = graph_repo.helpers.git(built.root, "ls-tree", "-r", "--name-only", built.shas["1b2c3d4"])
        self.assertNotIn("specs/SPEC-1.md", older)

    def test_a_tag_a_remote_and_a_shallow_clone_are_made(self):
        facts = {
            "spec": {"status": "draft"},
            "git": {
                "commits": [{"name": "c1", "holds": []}, {"name": "c2", "holds": []}],
                "tags": [{"name": "v1", "commit": "c1"}],
                "remote": True,
                "shallow": True,
            },
        }
        built = self.build(facts)
        self.assertEqual(graph_repo.helpers.git(built.root, "rev-list", "--count", "HEAD").strip(), "1", "a shallow clone holds one commit")

    def test_the_current_reader_builds_through_the_same_builder(self):
        self.assertTrue(lc.current_reads())


if __name__ == "__main__":
    unittest.main()
