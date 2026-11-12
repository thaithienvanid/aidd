"""An Intent's success criteria: an id and an address for each, a day read from the release and never stored, and what `aidd status`
and `aidd validate` say of them. Each table has a row that fails when the rule it names is removed."""

import datetime as dt
import unittest

import helpers  # noqa: F401  (puts src on sys.path)
from helpers import git
from product_scope_fixtures import CRITERION, PERSON, ScopeCase, intent, standing_outcomes

from aidd import workitems
from aidd.kernel import json_schema
from aidd.workitems import criteria, intents

D = dt.date
RESULT = {"measured_on": "2027-01-12", "actual": "90%", "source": "support report", "decision": "met"}


def day(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


class TheAddress(unittest.TestCase):
    def test_an_address_is_an_intent_a_hash_and_a_criterion(self):
        for text, want in (
            ("INTENT-1#S1", ("INTENT-1", "S1")),
            ("INTENT-12#S10", ("INTENT-12", "S10")),
            ("INTENT-1#", None),
            ("#S1", None),
            ("INTENT-1#S0", None),
            ("INTENT-1#s1", None),
            ("INTENT-1#S01", None),
            ("INTENT-1#S1#S2", None),
            ("INTENT-1#S1\n", None),
            ("INTENT-1 #S1", None),
            ("INTENT-1", None),
            ("", None),
            (None, None),
            (5, None),
        ):
            with self.subTest(text=text):
                self.assertEqual(criteria.parse_address(text), want)

    def test_an_address_and_an_id_read_the_schema_and_say_the_same_as_the_function(self):
        for cid in ("S1", "S9", "S10", "S0", "s1", "S", "1", "S1 ", "SS1"):
            with self.subTest(cid):
                self.assertEqual(criteria.is_id(cid), not json_schema.validate(cid, "common.schema.json#/$defs/criterion_id"))
        self.assertEqual(criteria.address("INTENT-3", "S2"), "INTENT-3#S2")

    def test_an_address_names_an_intent_by_the_same_id_the_schema_gives_every_item(self):
        for intent_id, valid in (("INTENT-1", True), ("INTENT_1.b:c", True), ("-INTENT", False), ("A" * 64, True), ("A" * 65, False)):
            with self.subTest(intent_id):
                self.assertEqual(criteria.parse_address(f"{intent_id}#S1") is not None, valid)


class TheDay(unittest.TestCase):
    RELEASE = D(2026, 12, 4)

    def test_the_day_is_the_last_release_plus_the_days_unless_a_person_chose_a_later_one(self):
        base = {"id": "S1", "measure_after_days": 14}
        for name, criterion, release, want, noted in (
            ("before a release", base, None, None, False),
            ("the release day plus the days", base, self.RELEASE, D(2026, 12, 18), False),
            ("one day", {**base, "measure_after_days": 1}, self.RELEASE, D(2026, 12, 5), False),
            ("a day chosen after the release", {**base, "measure_on": "2027-01-05"}, self.RELEASE, D(2027, 1, 5), False),
            ("a day chosen on the release day", {**base, "measure_on": "2026-12-04"}, self.RELEASE, D(2026, 12, 4), False),
            ("a day chosen before the release is ignored, with a note", {**base, "measure_on": "2026-12-03"}, self.RELEASE, D(2026, 12, 18), True),
            ("a day chosen, and no release yet", {**base, "measure_on": "2027-01-05"}, None, None, False),
            ("a day that is no day is ignored", {**base, "measure_on": "soon"}, self.RELEASE, D(2026, 12, 18), False),
            ("days in words", {**base, "measure_after_days": "14"}, self.RELEASE, None, False),
            ("no days", {"id": "S1"}, self.RELEASE, None, False),
            ("no days at all", {**base, "measure_after_days": 0}, self.RELEASE, None, False),
            ("true for days", {**base, "measure_after_days": True}, self.RELEASE, None, False),
        ):
            with self.subTest(name):
                found, note = criteria.measure_day(criterion, release)
                self.assertEqual(found, want)
                self.assertEqual(bool(note), noted)
                if noted:
                    self.assertIn("S1", note)
                    self.assertIn("2026-12-03", note)
                    self.assertIn("2026-12-04", note)

    def test_a_result_counts_unless_it_was_measured_before_the_last_release(self):
        for name, result, release, want in (
            ("no result", None, self.RELEASE, None),
            ("a result", RESULT, self.RELEASE, {"measured_on": "2027-01-12", "decision": "met"}),
            ("a result and no release day known: nothing counts", RESULT, None, None),
            ("measured on the release day", {**RESULT, "measured_on": "2026-12-04"}, self.RELEASE, {"measured_on": "2026-12-04", "decision": "met"}),
            ("measured the day before the release", {**RESULT, "measured_on": "2026-12-03"}, self.RELEASE, None),
            ("a result that is no mapping", "met", self.RELEASE, None),
            ("a result with no fields at all", {}, self.RELEASE, None),
            ("a result with no decision", {"measured_on": "2027-01-12"}, self.RELEASE, None),
            ("a result with no day", {"decision": "met"}, self.RELEASE, None),
        ):
            with self.subTest(name):
                self.assertEqual(criteria.result_of({"id": "S1", **({"result": result} if result is not None else {})}, release), want)


class TheLastRelease(unittest.TestCase):
    SPECS = {"SPEC-1": {"outcome": {"released_on": "2026-12-04"}}, "SPEC-2": {"outcome": {"released_on": "2026-12-10"}}, "SPEC-3": {}}
    LINES = {
        "SPEC-9": ({}, {}, {"id": "SPEC-9", "merged_in": "abc1234"}),
        "SPEC-8": ({}, {}, {"id": "SPEC-8"}),
        "SPEC-7": ({}, {}, {"id": "SPEC-7", "repo": "other/service", "merged_in": "abc1234"}),
        "SPEC-3": ({}, {}, {"id": "SPEC-3", "merged_in": "abc1234"}),
    }

    def read(self, kids: list[str], states: dict[str, str], merged: dict | None = None) -> dt.date | None:
        return criteria.last_release(kids, criteria.Work(states, self.SPECS, self.LINES, merged or {}))

    def test_it_is_the_last_release_where_users_are_and_nothing_while_any_work_waits(self):
        for name, kids, states, merged, want in (
            ("no work", [], {}, None, None),
            ("one released Spec", ["SPEC-1"], {"SPEC-1": "done"}, None, D(2026, 12, 4)),
            ("two, the later one counts", ["SPEC-1", "SPEC-2"], {"SPEC-1": "done", "SPEC-2": "done"}, None, D(2026, 12, 10)),
            ("one of two not released", ["SPEC-1", "SPEC-3"], {"SPEC-1": "done", "SPEC-3": "draft"}, None, None),
            ("a cancelled one is left out", ["SPEC-1", "SPEC-3"], {"SPEC-1": "done", "SPEC-3": "cancelled"}, None, D(2026, 12, 4)),
            ("every one cancelled", ["SPEC-3"], {"SPEC-3": "cancelled"}, None, None),
            ("a rolled-back one holds the day back", ["SPEC-1", "SPEC-2"], {"SPEC-1": "done", "SPEC-2": "rolled_back"}, None, None),
            ("a Spec built elsewhere, by its commit's day", ["SPEC-9"], {"SPEC-9": "done"}, {"abc1234": D(2026, 12, 8)}, D(2026, 12, 8)),
            ("its commit is not in the repository", ["SPEC-9"], {"SPEC-9": "done"}, {}, None),
            ("a planned Spec that records no commit", ["SPEC-8"], {"SPEC-8": "planned"}, {"abc1234": D(2026, 12, 8)}, None),
            (
                "a Spec with a file and no release day falls back to its line's commit",
                ["SPEC-3"],
                {"SPEC-3": "done"},
                {"abc1234": D(2026, 12, 8)},
                D(2026, 12, 8),
            ),
            (
                "a Spec built in another repository has no day here, even if a local commit has the name",
                ["SPEC-7"],
                {"SPEC-7": "done"},
                {"abc1234": D(2026, 12, 8)},
                None,
            ),
            ("another repository's work holds the day back from a released Spec", ["SPEC-1", "SPEC-7"], {"SPEC-1": "done", "SPEC-7": "done"}, {}, None),
            ("a file and a commit together", ["SPEC-1", "SPEC-9"], {"SPEC-1": "done", "SPEC-9": "done"}, {"abc1234": D(2026, 12, 8)}, D(2026, 12, 8)),
        ):
            with self.subTest(name):
                self.assertEqual(self.read(kids, states, merged), want)


class TheFiles(ScopeCase):
    """An Intent and its Spec, written as files in a repository, and read as `aidd status` and `aidd validate` read them."""

    def spec(self, number: int = 1, status: str = "done", released_on: str | None = "2027-01-02", parent: str = "INTENT-1") -> str:
        sid = f"SPEC-{number}-1"
        data = {
            "type": "spec",
            "id": sid,
            "title": "A slice",
            "status": status,
            "parent": parent,
            "change_type": "feat",
            "route": "normal",
            **({"outcome": {"released_on": released_on}} if released_on else {}),
        }
        self.write(f"specs/{sid}.md", data)
        return sid

    def intent_file(self, **extra) -> None:
        self.write("product/outcomes.md", standing_outcomes())
        self.write("product/intents/INTENT-1.md", intent("INTENT-1", serves="Outcome-1", **extra))

    def item(self, today: dt.date = dt.date(2027, 1, 15)) -> dict:
        found = workitems.open_work(self.root, self.config(), today=today, include_done=True)["items"]
        return next(i for i in found if i["id"] == "INTENT-1")

    def test_the_status_gives_each_criterion_its_address_and_its_own_day(self):
        self.intent_file(success_criteria=[CRITERION, {**CRITERION, "id": "S2", "measure_after_days": 7, "metric": {**CRITERION["metric"], "name": "Speed"}}])
        self.spec()
        item = self.item()
        self.assertEqual(
            item["criteria"],
            [
                {"id": "S1", "address": "INTENT-1#S1", "metric_name": "Wait", "measure_from": "2027-02-01", "result": None},
                {"id": "S2", "address": "INTENT-1#S2", "metric_name": "Speed", "measure_from": "2027-01-09", "result": None},
            ],
        )
        answer = workitems.open_work(self.root, self.config(), today=D(2027, 1, 15), include_done=True)
        self.assertEqual(json_schema.validate({"schema_version": "1", **answer}, "status.schema.json"), [])

    def test_the_day_is_null_before_a_release_and_a_criterion_has_no_next(self):
        self.intent_file()
        self.spec(released_on=None, status="in_progress")
        item = self.item()
        self.assertEqual(item["criteria"][0]["measure_from"], None)
        self.assertNotIn("next", item["criteria"][0])

    def test_the_day_moves_with_the_release_and_a_chosen_day_before_it_is_ignored(self):
        for name, changes, spec_day, want in (
            ("released on 2027-01-02", {}, "2027-01-02", "2027-02-01"),
            ("released a week later", {}, "2027-01-09", "2027-02-08"),
            ("a day chosen after it", {"measure_on": "2027-03-01"}, "2027-01-02", "2027-03-01"),
            ("a day chosen before it", {"measure_on": "2026-12-01"}, "2027-01-02", "2027-02-01"),
        ):
            with self.subTest(name):
                self.fresh()
                self.intent_file(success_criteria=[{**CRITERION, **changes}])
                self.spec(released_on=spec_day)
                self.assertEqual(self.item()["criteria"][0]["measure_from"], want)

    def test_a_planned_spec_built_elsewhere_gives_the_day_of_its_commit(self):
        self.start()
        self.write("README.md", "x\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "built elsewhere", env={"GIT_COMMITTER_DATE": "2027-01-06T12:00:00Z", "GIT_AUTHOR_DATE": "2027-01-06T12:00:00Z"})
        sha = git(self.root, "rev-parse", "HEAD").strip()
        data = intent("INTENT-1", serves="Outcome-1")
        data["phases"][0]["specs"][0]["merged_in"] = sha[:10]
        self.write("product/outcomes.md", standing_outcomes())
        self.write("product/intents/INTENT-1.md", data)
        self.assertEqual(self.item()["criteria"][0]["measure_from"], "2027-02-05")
        data["phases"][0]["specs"][0]["merged_in"] = "deadbeef"
        self.write("product/intents/INTENT-1.md", data)
        self.assertEqual(self.item()["criteria"][0]["measure_from"], None)

    def test_a_result_measured_before_the_last_release_is_discarded_and_one_after_it_counts(self):
        for name, measured, want in (("after", "2027-01-12", True), ("on the day", "2027-01-02", True), ("before", "2027-01-01", False)):
            with self.subTest(name):
                self.fresh()
                self.intent_file(success_criteria=[{**CRITERION, "result": {**RESULT, "measured_on": measured}}])
                self.spec()
                shown = self.item()["criteria"][0]["result"]
                self.assertEqual(shown, {"measured_on": measured, "decision": "met"} if want else None)

    def test_the_product_status_gives_the_decision_and_never_reached(self):
        self.intent_file(success_criteria=[{**CRITERION, "result": RESULT}], status="done")
        self.spec()
        shown = workitems.product_status(self.root, self.config())
        row = next(r for r in shown["intents"] if r["id"] == "INTENT-1")
        self.assertEqual(row["criteria"][0]["result"], {"measured_on": "2027-01-12", "decision": "met"})
        self.assertNotIn("reached", str(shown))
        self.assertNotIn("result", row)
        self.assertEqual(json_schema.validate({"schema_version": "1", **shown}, "product-status.schema.json"), [])
        self.assertIn("S1 met on 2027-01-12", workitems.product_status_text(shown))

    def test_validate_names_a_criterion_id_that_is_listed_twice_and_a_proposal_named_twice(self):
        for name, extra, expected in (
            ("an id twice", {"success_criteria": [CRITERION, {**CRITERION, "measure_after_days": 5}]}, "success criterion S1 is listed twice"),
            ("two ids", {"success_criteria": [CRITERION, {**CRITERION, "id": "S2"}]}, None),
            ("a proposal in both", {"proposal": "PROP-1", "from": "PROP-1"}, "`proposal` and `from` both name PROP-1"),
            ("a proposal and another source", {"proposal": "PROP-1", "from": "SPEC-4"}, None),
            ("a proposal alone", {"proposal": "PROP-1"}, None),
            ("a source alone", {"from": "PROP-1"}, None),
        ):
            with self.subTest(name):
                self.fresh()
                self.intent_file(**extra)
                errors, _, _ = self.repository_check()
                mine = [e for e in errors if "listed twice" in e or "both name" in e]
                self.assertEqual(bool(mine), expected is not None, mine)
                if expected:
                    self.assertTrue(any(expected in e for e in mine), mine)

    def test_validate_errors_on_a_from_address_whose_intent_lists_no_such_criterion(self):
        for name, source, wrong in (
            ("a criterion it lists", "INTENT-1#S1", False),
            ("a criterion it does not list", "INTENT-1#S2", True),
            ("an Intent in another repository", "INTENT-77#S9", False),
            ("an item id", "INTENT-1", False),
            ("a band", "band:checkout", False),
        ):
            with self.subTest(name):
                self.fresh()
                self.intent_file()
                self.write("product/intents/INTENT-2.md", {**intent("INTENT-2"), "from": source})
                errors, _, _ = self.repository_check()
                found = [e for e in errors if "`from` names" in e]
                self.assertEqual(bool(found), wrong, found)
                if wrong:
                    self.assertIn("INTENT-1 lists no criterion S2 (it lists S1)", found[0])

    def planned(self, *lines: dict) -> dict:
        """An Intent that serves, with one criterion that has a result measured on 2027-01-05, and the planned Spec lines given."""
        data = intent("INTENT-1", serves="Outcome-1")
        data["success_criteria"] = [{**CRITERION, "result": {**RESULT, "measured_on": "2027-01-05"}}]
        data["phases"][0]["specs"] = [{"title": "A slice", **line} for line in lines]
        return data

    def test_work_built_in_another_repository_has_no_day_here_so_no_result_counts_and_a_note_says_why(self):
        self.start()
        self.write("README.md", "x\n")
        self.commit("a commit of this repository that the other one's name happens to match")
        sha = git(self.root, "rev-parse", "HEAD").strip()
        self.write("product/outcomes.md", standing_outcomes())
        self.write("product/intents/INTENT-1.md", self.planned({"id": "SPEC-1", "repo": "other/service", "merged_in": sha}, {"id": "SPEC-2"}))
        self.write(
            "specs/SPEC-2.md", {"type": "spec", "id": "SPEC-2", "title": "S", "status": "done", "parent": "INTENT-1", "outcome": {"released_on": "2027-01-10"}}
        )
        shown = self.item()
        self.assertEqual(shown["criteria"][0]["measure_from"], None)
        self.assertEqual(shown["criteria"][0]["result"], None, "a result measured before the release may be true of older code, so it does not count")
        self.assertIn("SPEC-1 was built in another repository (other/service)", shown["criteria_note"])
        self.assertTrue(any("another repository" in n for n in self.repository_check()[2]))

    def test_a_merged_in_commit_this_clone_lacks_is_not_checked_and_no_result_counts(self):
        self.write("product/outcomes.md", standing_outcomes())
        self.write("product/intents/INTENT-1.md", self.planned({"id": "SPEC-1", "merged_in": "d" * 40}))
        shown = self.item()
        self.assertEqual((shown["criteria"][0]["measure_from"], shown["criteria"][0]["result"]), (None, None))
        self.assertIn("not in this clone", shown["criteria_note"])
        self.assertIn("fetch the history", shown["criteria_note"])
        self.assertTrue(any("fetch the history" in n for n in self.repository_check()[2]))

    def test_a_done_spec_with_no_release_day_gives_the_day_of_its_lines_commit(self):
        self.start()
        self.write("README.md", "x\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "built", env={"GIT_COMMITTER_DATE": "2027-01-06T12:00:00Z", "GIT_AUTHOR_DATE": "2027-01-06T12:00:00Z"})
        sha = git(self.root, "rev-parse", "HEAD").strip()
        self.write("product/outcomes.md", standing_outcomes())
        self.write("product/intents/INTENT-1.md", self.planned({"id": "SPEC-1", "merged_in": sha}))
        self.write("specs/SPEC-1.md", {"type": "spec", "id": "SPEC-1", "title": "S", "status": "done", "parent": "INTENT-1"})
        shown = self.item()
        self.assertEqual(shown["criteria"][0]["measure_from"], "2027-02-05")
        self.assertNotIn("criteria_note", shown)

    def test_the_product_status_counts_a_result_as_the_intents_status_shows_it(self):
        for name, measured_on, carried in (("measured after the last release", "2027-01-12", False), ("measured before it", "2027-01-05", True)):
            with self.subTest(name):
                self.fresh()
                self.write("product/outcomes.md", standing_outcomes())
                data = intent("INTENT-1", serves="Outcome-1", status="done", success_criteria=[{**CRITERION, "result": {**RESULT, "measured_on": measured_on}}])
                self.write("product/intents/INTENT-1.md", data)
                self.spec(released_on="2027-01-10")
                shown = workitems.product_status(self.root, self.config())
                row = shown["intents"][0]["criteria"][0]["result"]
                self.assertEqual(row is not None, not carried)
                self.assertEqual(
                    "Outcome-1" in [i["id"] for i in shown["stalled"]],
                    not carried,
                    "stalled when the Intent holds all its results, and carried while one is to be measured again",
                )
                answer = workitems.open_work(self.root, self.config(), today=D(2027, 3, 1), include_done=True)
                self.assertEqual("Outcome-1" in [i["id"] for i in answer["product_scope"]["stalled"]], not carried)

    def test_validate_errors_on_a_from_that_names_the_item_itself(self):
        for name, source, wrong in (
            ("its own criterion", "INTENT-1#S1", True),
            ("its own id", "INTENT-1", True),
            ("another Intent's criterion", "INTENT-2#S1", False),
        ):
            with self.subTest(name):
                self.fresh()
                self.intent_file(**{"from": source})
                self.write("product/intents/INTENT-2.md", intent("INTENT-2", serves="Outcome-1"))
                errors, _, _ = self.repository_check()
                self.assertEqual(any("this item itself" in e for e in errors), wrong, errors)

    def test_validate_notes_a_chosen_day_that_it_ignores_and_names_the_day_it_reads(self):
        self.intent_file(success_criteria=[{**CRITERION, "measure_on": "2026-12-01"}])
        self.spec()
        errors, warnings, notes = self.repository_check()
        mine = [n for n in notes if "measure_on" in n]
        self.assertEqual(len(mine), 1, (errors, warnings, notes))
        self.assertIn("2026-12-01", mine[0])
        self.assertIn("2027-01-02", mine[0])
        self.assertIn("2027-02-01", mine[0])
        self.fresh()
        self.intent_file(success_criteria=[{**CRITERION, "measure_on": "2027-03-01"}])
        self.spec()
        self.assertEqual([n for n in self.repository_check()[2] if "measure_on" in n], [])

    def test_a_file_with_the_retired_success_check_fails_with_the_schemas_own_error(self):
        self.write("product/outcomes.md", standing_outcomes())
        data = intent("INTENT-1")
        data["success_check"] = {"metric": CRITERION["metric"], "measure_after_days": 30}
        self.write("product/intents/INTENT-1.md", data)
        errors, _, _ = self.repository_check()
        self.assertTrue(any("unknown field 'success_check'" in e and "success_criteria" in e for e in errors), errors)

    def test_an_intent_that_serves_with_no_criteria_is_refused_and_says_what_to_add(self):
        self.write("product/outcomes.md", standing_outcomes())
        self.write("product/intents/INTENT-1.md", {**intent("INTENT-1"), "serves": "Outcome-1"})
        errors, _, _ = self.repository_check()
        self.assertTrue(any("success_criteria" in e for e in errors), errors)


class WhatAnAgreementCoversOfACriterion(unittest.TestCase):
    """A criterion changed after the person agreed asks for the agreement again, but the agent's drafted result does not."""

    BASE = intent("INTENT-1", serves="Outcome-1")

    def changes(self, then_criteria: list, now_criteria: list) -> list[str]:
        return intents.changes_since({**self.BASE, "success_criteria": then_criteria}, {**self.BASE, "success_criteria": now_criteria})

    def test_each_edit_to_a_criterion_has_its_row(self):
        approved = {**RESULT, "approval": {"by": PERSON, "at": "2027-01-13T09:00:00Z"}}
        for name, then, now, want in (
            ("as agreed", [CRITERION], [CRITERION], []),
            ("a metric edited", [CRITERION], [{**CRITERION, "metric": {**CRITERION["metric"], "target": "2 days"}}], ["its success criteria changed"]),
            ("a criterion renumbered", [CRITERION], [{**CRITERION, "id": "S2"}], ["its success criteria changed"]),
            (
                "an id reused for another measure",
                [CRITERION, {**CRITERION, "id": "S2"}],
                [CRITERION, {**CRITERION, "id": "S2", "measure_after_days": 5}],
                ["its success criteria changed"],
            ),
            ("a criterion added", [CRITERION], [CRITERION, {**CRITERION, "id": "S2"}], ["its success criteria changed"]),
            ("a criterion removed", [CRITERION, {**CRITERION, "id": "S2"}], [CRITERION], ["its success criteria changed"]),
            ("a day chosen", [CRITERION], [{**CRITERION, "measure_on": "2027-02-01"}], ["its success criteria changed"]),
            ("a result drafted: the agent's own, so no change", [CRITERION], [{**CRITERION, "result": RESULT}], []),
            (
                "a result drafted with its approval: a person's yes, so a change",
                [CRITERION],
                [{**CRITERION, "result": approved}],
                ["its success criteria changed"],
            ),
            ("a drafted result edited", [{**CRITERION, "result": RESULT}], [{**CRITERION, "result": {**RESULT, "actual": "10%"}}], ["its result changed"]),
            ("a drafted result removed", [{**CRITERION, "result": RESULT}], [CRITERION], ["its result changed"]),
            ("a drafted result that fails its schema", [CRITERION], [{**CRITERION, "result": {**RESULT, "decision": "maybe"}}], ["its result changed"]),
            (
                "an approved result edited",
                [{**CRITERION, "result": approved}],
                [{**CRITERION, "result": {**approved, "actual": "10%"}}],
                ["its success criteria changed"],
            ),
        ):
            with self.subTest(name):
                self.assertEqual(self.changes(then, now), want)


if __name__ == "__main__":
    unittest.main()
