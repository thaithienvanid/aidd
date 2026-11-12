"""The schemas of the product scope: the BRD, the PRD, the standing outcomes, and the intent order; what an Intent
gains (`serves`, `success_criteria`) and loses (`priority`); the Intent's derived `approved` status; the `product_dir`
setting; and the step codes that go with them. Each constraint has a row that fails when the constraint is removed."""

import copy
import re
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts src on sys.path)
from helpers import ROOT

from aidd import config
from aidd.kernel import json_schema, resources
from aidd.workitems import spec_file, steps

SCOPE = "product-scope.schema.json"
INTENT = "intent.schema.json"
PERSON = "Dana <dana@example.com>"
METRIC = {"name": "Tickets answered within a day", "source": "support report", "baseline": "40%", "target": "80%"}
RESULT = {"measured_on": "2027-01-11", "actual": "45%", "source": "support report", "decision": "continue"}
OBJECTIVE = {"id": "Objective-1", "title": "Answer support faster", "metric": METRIC, "due": "2027-06-30", "results": [RESULT]}
REQUIREMENT = {"id": "Requirement-1", "title": "Customers reach an answer", "serves": "Objective-1"}
BARE_REQUIREMENT = {"id": "Requirement-1", "title": "Customers reach an answer"}
OUTCOME = {"id": "Outcome-1", "title": "Customers get a quick answer", "metric": METRIC, "serves": "Requirement-1"}
STANDING = {"id": "Outcome-1", "title": "Answers stay quick", "metric": {k: v for k, v in METRIC.items() if k != "baseline"}}
APPROVAL = {"approved_by": PERSON, "approved_at": "2026-11-13T09:00:00Z"}
BRD = {"type": "brd", "sponsor": PERSON, "objectives": [OBJECTIVE], "requirements": [REQUIREMENT], **APPROVAL}
PRD = {"type": "prd", "outcomes": [OUTCOME], "review_due": "2027-02-01"}
STANDING_OUTCOMES = {"type": "standing-outcomes", "outcomes": [STANDING]}
ORDER = {"type": "intent-order", "owner": PERSON, "order": ["INTENT-3", "INTENT-1"], "max_in_flight": 4, "review_every_days": 30}
INTENT_FIELDS = {
    "type": "intent",
    "id": "INTENT-1",
    "title": "Quicker answers",
    "outcome": "Customers wait under a day.",
    "serves": "Outcome-2",
    "success_criteria": [{"id": "S1", "metric": {"name": "Wait", "source": "support report", "target": "1 day"}, "measure_after_days": 30}],
}
FROM_THE_DISK = sorted((ROOT / "tests" / "fixtures" / "migration" / "today" / "specs").glob("INT-*.md"))


def changed(base: dict, **changes) -> dict:
    """`base` with each change applied; a value of `...` removes the key. A dotted key reaches into a mapping or a list."""
    doc = copy.deepcopy(base)
    for path, value in changes.items():
        *parents, last = path.split(".")
        node = doc
        for part in parents:
            node = node[int(part)] if isinstance(node, list) else node[part]
        if value is ...:
            node.pop(last, None)
        elif isinstance(node, list):
            node[int(last)] = value
        else:
            node[last] = value
    return doc


def problems(doc: dict, schema: str = SCOPE) -> list[str]:
    return json_schema.validate(doc, schema)


class TheDocuments(unittest.TestCase):
    def check(self, rows, base):
        for what, changes, expected in rows:
            with self.subTest(what):
                found = problems(changed(base, **changes))
                if expected is None:
                    self.assertEqual(found, [])
                else:
                    self.assertTrue(any(expected in line for line in found), f"{expected!r} not in {found}")

    def test_each_shape_of_a_product_scope_is_whole(self):
        for name, doc in (("a BRD", BRD), ("a PRD", PRD), ("standing outcomes", STANDING_OUTCOMES), ("the intent order", ORDER)):
            with self.subTest(name):
                self.assertEqual(problems(doc), [])

    def test_a_file_names_one_of_the_four_types(self):
        for what, doc in (
            ("no type", {k: v for k, v in PRD.items() if k != "type"}),
            ("another type", {**PRD, "type": "spec"}),
            ("an empty one", {"type": ""}),
        ):
            with self.subTest(what):
                self.assertTrue(problems(doc))
        for name, doc in (("a BRD", BRD), ("a PRD", PRD), ("standing outcomes", STANDING_OUTCOMES), ("the order", ORDER)):
            with self.subTest(name):
                self.assertEqual(problems({**doc, "stray": 1}), ["$: unknown field 'stray'"])

    def test_a_brd(self):
        self.check(
            [
                ("no sponsor", {"sponsor": ...}, "missing required field 'sponsor'"),
                ("no objectives, for a brief with no measure", {"objectives": ...}, None),
                ("no requirements", {"requirements": ...}, "missing required field 'requirements'"),
                ("an empty list of objectives", {"objectives": []}, "at least 1"),
                ("an empty list of requirements", {"requirements": []}, "at least 1"),
                ("outcomes belong to the PRD", {"outcomes": [OUTCOME]}, "unknown field 'outcomes'"),
                ("a status is derived, never stored", {"objectives.0.status": "met"}, "unknown field 'status'"),
                ("a requirement's status is derived too", {"requirements.0.status": "met"}, "unknown field 'status'"),
                ("an empty sponsor", {"sponsor": ""}, "shorter than 1"),
                ("an objective with no date", {"objectives.0.due": ...}, "missing required field 'due'"),
                ("a placeholder for a date", {"objectives.0.due": "TODO"}, "not a valid ISO date"),
                ("a date that is no day", {"objectives.0.due": "2027-02-30"}, "due"),
                ("an objective with no metric", {"objectives.0.metric": ...}, "missing required field 'metric'"),
                ("a requirement that serves nothing: `aidd validate` asks for it only where objectives exist", {"requirements.0.serves": ...}, None),
                ("a requirement that serves an id that is no objective", {"requirements.0.serves": "Outcome-1"}, "serves"),
                ("the smallest BRD, a sponsor and requirements", {"objectives": ..., "requirements.0.serves": ...}, None),
            ],
            BRD,
        )

    def test_an_id_is_its_kind_and_the_next_free_number(self):
        for field, item, ok, wrong in (
            ("objectives", 0, "Objective-12", ("Objective-0", "Objective-01", "objective-1", "Objective-", "Objective-1a", "Outcome-1", "Requirement-1", "")),
            ("requirements", 0, "Requirement-2", ("Requirement-0", "Requirement-01", "Objective-1")),
        ):
            for value in (ok, *wrong):
                with self.subTest(field=field, id=value):
                    found = problems(changed(BRD, **{f"{field}.{item}.id": value}))
                    self.assertEqual(not found, value == ok, found)
        for value in ("Outcome-3", "Outcome-30"):
            self.assertEqual(problems(changed(PRD, **{"outcomes.0.id": value})), [], value)
        for value in ("Outcome-0", "Objective-1", "outcome-1"):
            self.assertTrue(problems(changed(PRD, **{"outcomes.0.id": value})), value)

    def test_what_an_item_serves_is_the_kind_above_it(self):
        for kind, base, path, ok, wrong in (
            ("requirement", BRD, "requirements.0.serves", ("Objective-2",), ("Requirement-1", "Outcome-1", "Objective-0", "")),
            ("outcome", PRD, "outcomes.0.serves", ("Requirement-1", "Objective-1"), ("Outcome-1", "Requirement-0", "Intent-1", "")),
        ):
            for value in ok:
                self.assertEqual(problems(changed(base, **{path: value})), [], f"{kind} serves {value}")
            for value in wrong:
                with self.subTest(kind=kind, serves=value):
                    self.assertTrue(problems(changed(base, **{path: value})))
        self.assertEqual(problems(changed(PRD, **{"outcomes.0.serves": ...})), [], "an outcome of a PRD with no BRD may serve nothing in the file")

    def test_a_metric_names_where_it_is_measured(self):
        for what, base, path, changes, valid in (
            ("whole", BRD, "objectives.0.metric", {}, True),
            ("no source", BRD, "objectives.0.metric", {"source": ...}, False),
            ("no target", BRD, "objectives.0.metric", {"target": ...}, False),
            ("no name", BRD, "objectives.0.metric", {"name": ...}, False),
            ("no baseline on an objective", BRD, "objectives.0.metric", {"baseline": ...}, False),
            ("none: new product", BRD, "objectives.0.metric", {"baseline": "none: new product"}, True),
            ("no baseline on an outcome", PRD, "outcomes.0.metric", {"baseline": ...}, False),
            ("no baseline on a standing outcome, which is held to a threshold", STANDING_OUTCOMES, "outcomes.0.metric", {"baseline": ...}, True),
            ("a baseline on a standing outcome", STANDING_OUTCOMES, "outcomes.0.metric", {"baseline": "40%"}, True),
            ("an empty source", BRD, "objectives.0.metric", {"source": ""}, False),
            ("an empty target", BRD, "objectives.0.metric", {"target": ""}, False),
            ("a number where a string goes", BRD, "objectives.0.metric", {"target": 80}, False),
            ("a key the metric does not know", BRD, "objectives.0.metric", {"unit": "%"}, False),
        ):
            with self.subTest(what):
                doc = changed(base, **{f"{path}.{k}": v for k, v in changes.items()})
                self.assertEqual(not problems(doc), valid, problems(doc))

    def test_a_result_holds_a_number_and_its_source_unless_the_item_is_retired_and_a_requirement_needs_only_its_source(self):
        number = {"actual": "45%", "source": "support report"}
        # (what, the entry, valid for an objective or an outcome, valid for a requirement, which has no metric to read a number from)
        for what, entry, valid, valid_for_requirement in (
            ("met, with its number and source", {"decision": "met", **number}, True, True),
            ("continue, with its number and source", {"decision": "continue", **number}, True, True),
            ("change_target, with its number and source", {"decision": "change_target", **number}, True, True),
            ("met with no number", {"decision": "met", "source": "r"}, False, True),
            ("met with no source", {"decision": "met", "actual": "45%"}, False, False),
            ("met with neither", {"decision": "met"}, False, False),
            ("continue with neither", {"decision": "continue"}, False, True),
            ("continue with a source only", {"decision": "continue", "source": "r"}, False, True),
            ("retire with neither", {"decision": "retire"}, True, True),
            ("retire with both", {"decision": "retire", **number}, True, True),
            ("a decision that is no decision", {"decision": "done", **number}, False, False),
            ("no decision", dict(number), False, False),
            ("a date that is no day", {"decision": "met", **number, "measured_on": "2027-02-30"}, False, False),
            ("a key the result does not know", {"decision": "met", **number, "status": "met"}, False, False),
            ("an empty number", {"decision": "met", "actual": "", "source": "r"}, False, False),
        ):
            entry = {"measured_on": "2027-01-11", **entry}
            for base, path, expected in (
                (BRD, "objectives.0.results", valid),
                (BRD, "requirements.0.results", valid_for_requirement),
                (PRD, "outcomes.0.results", valid),
                (STANDING_OUTCOMES, "outcomes.0.results", valid),
            ):
                with self.subTest(what=what, where=path):
                    doc = changed(base, **{path: [entry]})
                    self.assertEqual(not problems(doc), expected, problems(doc))
        for path in ("objectives.0.results", "requirements.0.results"):
            with self.subTest(where=path, what="no date"):
                self.assertTrue(problems(changed(BRD, **{path: [{"decision": "retire"}]})), "a result says when it was measured")

    def test_a_title_is_a_line_of_at_most_120_characters_as_every_other_title_is(self):
        for field, base in (("objectives", BRD), ("requirements", BRD), ("outcomes", PRD), ("outcomes", STANDING_OUTCOMES)):
            for what, title, valid in (("one character", "x", True), ("120", "x" * 120, True), ("121", "x" * 121, False), ("empty", "", False)):
                with self.subTest(field=field, title=what):
                    self.assertEqual(not problems(changed(base, **{f"{field}.0.title": title})), valid)
        self.assertEqual(resources.load_json(INTENT)["properties"]["title"]["maxLength"], 120)

    def test_a_prd_holds_outcomes_and_may_hold_objectives(self):
        self.check(
            [
                ("no outcomes", {"outcomes": ...}, "missing required field 'outcomes'"),
                ("an empty list of outcomes", {"outcomes": []}, "at least 1"),
                ("objectives, when no BRD exists", {"objectives": [OBJECTIVE]}, None),
                ("requirements, when no BRD exists", {"requirements": [BARE_REQUIREMENT]}, None),
                ("requirements that serve an objective of the PRD", {"objectives": [OBJECTIVE], "requirements": [REQUIREMENT]}, None),
                ("an empty list of requirements", {"requirements": []}, "at least 1"),
                ("a requirement with no id", {"requirements": [{"title": "T"}]}, "missing required field 'id'"),
                ("a sponsor belongs to the BRD", {"sponsor": PERSON}, "unknown field 'sponsor'"),
                ("an outcome with no metric", {"outcomes.0.metric": ...}, "missing required field 'metric'"),
                ("a status is derived, never stored", {"outcomes.0.status": "active"}, "unknown field 'status'"),
                ("a review date that is no day", {"review_due": "2027-13-01"}, "review_due"),
            ],
            PRD,
        )

    def test_standing_outcomes_are_held_to_a_threshold(self):
        self.check(
            [
                ("no outcomes", {"outcomes": ...}, "missing required field 'outcomes'"),
                ("an outcome serves nothing, for nothing is above it", {"outcomes.0.serves": "Requirement-1"}, "unknown field 'serves'"),
                ("objectives belong to the BRD or the PRD", {"objectives": [OBJECTIVE]}, "unknown field 'objectives'"),
                ("requirements, when no BRD exists", {"requirements": [BARE_REQUIREMENT]}, None),
                ("an empty list of requirements", {"requirements": []}, "at least 1"),
                ("a requirement that stores a status", {"requirements": [{**REQUIREMENT, "status": "met"}]}, "unknown field 'status'"),
                ("a status is derived, never stored", {"outcomes.0.status": "met"}, "unknown field 'status'"),
            ],
            STANDING_OUTCOMES,
        )

    def test_a_file_names_who_approved_it_and_when_or_neither(self):
        approved = {"approved_by": PERSON, "approved_at": "2026-11-13T09:00:00+02:00"}
        for name, base in (("a BRD", BRD), ("a PRD", PRD), ("standing outcomes", STANDING_OUTCOMES), ("the order", ORDER)):
            plain = {k: v for k, v in base.items() if k not in APPROVAL}
            for what, extra, valid in (
                ("neither", {}, True),
                ("both", approved, True),
                ("who, with no time", {"approved_by": PERSON}, False),
                ("a time, with no one", {"approved_at": "2026-11-13T09:00:00Z"}, False),
                ("a time that is only a day", {**approved, "approved_at": "2026-11-13"}, False),
                ("a time with no zone", {**approved, "approved_at": "2026-11-13T09:00:00"}, False),
                ("a time that is no time", {**approved, "approved_at": "2026-13-13T09:00:00Z"}, False),
            ):
                with self.subTest(name=name, what=what):
                    self.assertEqual(not problems({**plain, **extra}), valid, problems({**plain, **extra}))

    def test_the_order_of_the_intents(self):
        self.check(
            [
                ("no product owner", {"owner": ...}, "missing required field 'owner'"),
                ("no order", {"order": ...}, "missing required field 'order'"),
                ("an empty order", {"order": []}, None),
                ("one Intent twice", {"order": ["INTENT-1", "INTENT-1"]}, "unique"),
                ("an id that is no id", {"order": ["INTENT 1"]}, "does not match"),
                ("no limit in flight", {"max_in_flight": ...}, None),
                ("a limit of none", {"max_in_flight": 0}, "below minimum 1"),
                ("a limit of one", {"max_in_flight": 1}, None),
                ("a limit in words", {"max_in_flight": "four"}, "integer"),
                ("no review cycle", {"review_every_days": ...}, None),
                ("a review cycle of no days", {"review_every_days": 0}, "below minimum 1"),
                ("a key the order does not know", {"priority": {"INTENT-1": "high"}}, "unknown field 'priority'"),
            ],
            ORDER,
        )
        cycle = resources.load_json(SCOPE)["$defs"]["intent_order"]["properties"]["review_every_days"]
        self.assertEqual(cycle["default"], 30)


class TheIntent(unittest.TestCase):
    def test_what_an_intent_serves_and_how_it_is_checked(self):
        for what, changes, valid in (
            ("a product outcome", {}, True),
            ("a requirement, when there is no PRD", {"serves": "Requirement-2"}, True),
            ("a standing outcome, whose id is an outcome's", {"serves": STANDING["id"]}, True),
            ("an objective, which only an outcome serves", {"serves": "Objective-1"}, False),
            ("an id that is no item", {"serves": "INTENT-2"}, False),
            ("an id that is not numbered from 1", {"serves": "Outcome-0"}, False),
            ("two ids", {"serves": ["Outcome-1", "Outcome-2"]}, False),
            ("serves with no success criteria", {"success_criteria": ...}, False),
            ("serves with an empty list of them", {"success_criteria": []}, False),
            ("serves and covers together, a product outcome and the needs of a proposal", {"covers": ["NEED-1"]}, True),
            ("covers alone, for client work", {"serves": ..., "success_criteria": ..., "covers": ["NEED-1"]}, True),
            ("neither, as before", {"serves": ..., "success_criteria": ...}, True),
            ("success criteria without serves", {"serves": ...}, True),
            (
                "the retired `success_check`, which fails with the schema's own error",
                {"success_check": {"metric": {"name": "Wait", "source": "support report", "target": "1 day"}, "measure_after_days": 30}},
                False,
            ),
        ):
            with self.subTest(what):
                doc = changed(INTENT_FIELDS, **changes)
                self.assertEqual(not problems(doc, INTENT), valid, problems(doc, INTENT))

    def test_a_criterion_is_an_id_a_metric_and_the_days_to_wait(self):
        for what, changes, valid in (
            ("one criterion", {}, True),
            (
                "a second, with the next id",
                {
                    "success_criteria": [
                        *INTENT_FIELDS["success_criteria"],
                        {"id": "S2", "metric": {"name": "A", "source": "b", "target": "c"}, "measure_after_days": 7},
                    ]
                },
                True,
            ),
            ("an id that is not `S` and a number", {"success_criteria.0.id": "1"}, False),
            ("an id from zero", {"success_criteria.0.id": "S0"}, False),
            ("an id in lower case", {"success_criteria.0.id": "s1"}, False),
            ("an id with a leading zero", {"success_criteria.0.id": "S01"}, False),
            ("an id past nine", {"success_criteria.0.id": "S10"}, True),
            ("no id", {"success_criteria.0.id": ...}, False),
            ("no days", {"success_criteria.0.measure_after_days": ...}, False),
            ("no days at all", {"success_criteria.0.measure_after_days": 0}, False),
            ("one day", {"success_criteria.0.measure_after_days": 1}, True),
            ("days in words", {"success_criteria.0.measure_after_days": "30"}, False),
            ("no metric", {"success_criteria.0.metric": ...}, False),
            ("a metric with no source", {"success_criteria.0.metric.source": ...}, False),
            ("a metric with no baseline, which an Intent need not name", {"success_criteria.0.metric.baseline": ...}, True),
            ("a day chosen", {"success_criteria.0.measure_on": "2027-02-01"}, True),
            ("a day chosen that is no day", {"success_criteria.0.measure_on": "2027-02-31"}, False),
            ("a day chosen in words", {"success_criteria.0.measure_on": "soon"}, False),
            ("a key a criterion does not know", {"success_criteria.0.unit": "%"}, False),
            ("a status, which a criterion does not have", {"success_criteria.0.status": "open"}, False),
            ("success criteria that are no list", {"success_criteria": {"id": "S1"}}, False),
        ):
            with self.subTest(what):
                doc = changed(INTENT_FIELDS, **changes)
                self.assertEqual(not problems(doc, INTENT), valid, problems(doc, INTENT))

    def test_a_result_sits_on_its_criterion_and_says_what_a_person_decided(self):
        result = {
            "measured_on": "2027-03-01",
            "actual": "1 day",
            "source": "support report",
            "decision": "met",
            "approval": {"by": PERSON, "at": "2027-03-02T09:00:00Z"},
        }
        where = "success_criteria.0.result"
        for what, value, valid in (
            ("whole", result, True),
            ("a draft with no approval", {k: v for k, v in result.items() if k != "approval"}, True),
            ("each of the four decisions", {**result, "decision": "continue"}, True),
            ("a decision to retire needs no number", {"measured_on": "2027-03-01", "decision": "retire"}, True),
            ("no decision", {k: v for k, v in result.items() if k != "decision"}, False),
            ("a decision that is no word of the four", {**result, "decision": "yes"}, False),
            ("the retired `reached`", {**result, "reached": True}, False),
            ("the retired `follow_up`", {**result, "follow_up": "INTENT-9"}, False),
            ("no number", {k: v for k, v in result.items() if k != "actual"}, False),
            ("no source", {k: v for k, v in result.items() if k != "source"}, False),
            ("no date", {k: v for k, v in result.items() if k != "measured_on"}, False),
            ("an approval with no person", {**result, "approval": {"at": "2027-03-02T09:00:00Z"}}, False),
            ("an approval with no instant", {**result, "approval": {"by": PERSON}}, False),
            ("an approval in the loose pair", {**result, "approved_by": PERSON}, False),
        ):
            with self.subTest(what):
                doc = changed(INTENT_FIELDS, **{where: value})
                self.assertEqual(not problems(doc, INTENT), valid, problems(doc, INTENT))
        for old in ("result", "success_check"):
            with self.subTest(f"`{old}` on the Intent itself"):
                self.assertTrue(problems({**INTENT_FIELDS, old: result}, INTENT))

    def test_what_raised_an_intent_and_the_day_it_starts(self):
        for what, changes, valid in (
            ("nothing", {}, True),
            ("an item id", {"from": "SPEC-4"}, True),
            ("a criterion's address", {"from": "INTENT-1#S1"}, True),
            ("a band", {"from": "band:checkout-conversion"}, True),
            ("a link", {"from": "https://example.com/browse/PORT-31"}, True),
            ("free text", {"from": "the owner said so in a call"}, False),
            ("an address with no criterion", {"from": "INTENT-1#"}, False),
            ("an address with no Intent", {"from": "#S1"}, False),
            ("an address with a criterion from zero", {"from": "INTENT-1#S0"}, False),
            ("an address with a lower-case criterion", {"from": "INTENT-1#s1"}, False),
            ("a link with no scheme", {"from": "example.com/x"}, False),
            ("two", {"from": ["SPEC-4", "SPEC-5"]}, False),
            ("a start day", {"start_on": "2027-01-04"}, True),
            ("a start day that is no day", {"start_on": "2027-13-04"}, False),
            ("a start in words", {"start_on": "in January"}, False),
            ("a proposal and `from` side by side", {"proposal": "PROP-1", "from": "INTENT-0"}, True),
        ):
            with self.subTest(what):
                doc = changed(INTENT_FIELDS, **changes)
                self.assertEqual(not problems(doc, INTENT), valid, problems(doc, INTENT))

    def test_an_intent_that_was_valid_before_is_valid_now_but_for_its_priority(self):
        for path in FROM_THE_DISK:
            with self.subTest(path.name):
                _, _, errors = spec_file.load_object(path.read_text(encoding="utf-8"), path.name)
                self.assertEqual(errors, [])
        base = {"type": "intent", "id": "INTENT-1", "title": "t", "outcome": "g"}
        self.assertEqual(problems(base, INTENT), [])

    def test_an_intent_has_no_priority_and_a_spec_keeps_its_own(self):
        text = "---\ntype: intent\nid: INTENT-1\ntitle: t\noutcome: g\npriority: high\n---\n\nbody\n"
        _, _, errors = spec_file.load_object(text, "product/intents/INTENT-1.md")
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("unknown field 'priority'", errors[0])
        self.assertIn("priority", resources.load_json("spec.schema.json")["properties"])

    def test_approved_is_derived_and_never_stored(self):
        base = {"type": "intent", "id": "INTENT-1", "title": "t", "outcome": "g"}
        for value, valid in (("draft", True), ("active", True), ("done", True), ("cancelled", True), ("approved", False), ("started", False), ("", False)):
            with self.subTest(status=value):
                self.assertEqual(not problems({**base, "status": value}, INTENT), valid, problems({**base, "status": value}, INTENT))
        found = problems({**base, "status": "approved"}, INTENT)
        self.assertEqual(found, ["$.status: not allowed"])

    def test_the_refusals_of_approved_and_of_an_objective_say_why_and_what_to_do(self):
        head = "---\ntype: intent\nid: INTENT-1\ntitle: t\noutcome: g\n"
        check = "  - id: S1\n    metric: {name: Wait, source: report, target: one day}\n"
        for what, extra, expected in (
            ("a stored approved", "status: approved\n", ("`approved` is derived from `approval`", "remove the `status` line", "`aidd approve <ID>`")),
            (
                "an objective",
                "serves: Objective-1\nsuccess_criteria:\n" + check + "    measure_after_days: 30\n",
                ("(`Outcome-n`)", "`Requirement-n`", "served through the outcome or requirement"),
            ),
            ("an id that is no item", "serves: INTENT-2\nsuccess_criteria:\n" + check + "    measure_after_days: 30\n", ("(`Outcome-n`)", "INTENT-2")),
        ):
            with self.subTest(what):
                _, _, errors = spec_file.load_object(head + extra + "---\n\nbody\n", "product/intents/INTENT-1.md")
                self.assertEqual(len(errors), 1, errors)
                for part in expected:
                    self.assertIn(part, errors[0])
        _, _, errors = spec_file.load_object(head + "status: bogus\n---\n\nbody\n", "product/intents/INTENT-1.md")
        self.assertTrue(errors and "derived" not in errors[0], "another bad status keeps the schema's own message")

    def test_a_file_that_says_approved_is_read_as_it_was_before_the_status_existed(self):
        from aidd.workitems import status as workitem_status

        for what, data, children, expected in (
            ("stored approved, no slices", {"status": "approved"}, [], "draft"),
            ("stored approved, a slice not started", {"status": "approved"}, ["draft"], "draft"),
            ("stored approved, a slice started", {"status": "approved"}, ["in_progress"], "active"),
            ("stored approved, a person closed it", {"status": "approved", "go_no_go": {"decision": "no_go"}}, [], "cancelled"),
            ("stored active, no slices, as before", {"status": "active"}, [], "active"),
            ("stored draft, as before", {"status": "draft"}, [], "draft"),
            ("stored done", {"status": "done"}, ["draft"], "done"),
            ("no status", {}, [], "draft"),
        ):
            with self.subTest(what):
                self.assertEqual(workitem_status.intent_status(data, children), expected)


class TheStatuses(unittest.TestCase):
    def test_approved_stands_between_draft_and_active_and_has_its_group(self):
        table = config.status_table("intent")
        self.assertEqual(table["enum"], ["draft", "approved", "active", "done", "cancelled"])
        self.assertEqual(table["x-groups"]["approved"], "unstarted")
        self.assertTrue(table["x-meanings"]["approved"].startswith("Derived"))
        self.assertEqual(config.status_set("intent", "can_wait"), {"draft", "approved", "active"})
        self.assertEqual(config.status_set("intent", "ended"), {"done", "cancelled"})
        self.assertEqual(config.status_set("intent", "never_stored"), {"approved"})

    def test_the_move_to_approved_sets_the_approval(self):
        moves = [m for m in config.status_transitions("intent") if m["to"] == "approved"]
        self.assertEqual([(m["from"], m["who"], m["requires"]) for m in moves], [(["draft"], "person", ["approval"])])

    def test_every_status_can_be_entered_and_left_but_the_closed_ones_which_a_person_reopens(self):
        table = config.status_table("intent")
        moves = config.status_transitions("intent")
        entered = {m["to"] for m in moves} | {table["x-initial"]["status"]}
        left = {s for m in moves for s in m["from"]}
        for status in table["enum"]:
            with self.subTest(status=status):
                self.assertIn(status, entered)
                self.assertTrue(status in left or status == "cancelled", f"{status} leads nowhere")
        for status in ("draft", "approved"):
            self.assertEqual(
                {m["who"] for m in moves if status in m["from"] and m["to"] == "active"}, {"agent"}, "a slice starting is derived, never a person's move"
            )


class TheFamilies(unittest.TestCase):
    """One owner for each fact: each place that names a kind of item, an id, or a part of a measurement reads the same definition."""

    def defs(self) -> dict:
        return resources.load_json(SCOPE)["$defs"]

    def test_the_kinds_an_item_serves_are_the_ids_of_the_kinds_above_it(self):
        defs = self.defs()
        pointer = "#/$defs/"
        self.assertEqual(defs["requirement"]["properties"]["serves"]["$ref"], pointer + "objective_id")
        self.assertEqual([r["$ref"] for r in defs["product_outcome"]["properties"]["serves"]["oneOf"]], [pointer + "requirement_id", pointer + "objective_id"])
        served = resources.load_json(INTENT)["properties"]["serves"]["oneOf"]
        self.assertEqual(
            [r["$ref"] for r in served], ["urn:aidd:1:product-scope" + pointer + "outcome_id", "urn:aidd:1:product-scope" + pointer + "requirement_id"]
        )

    def test_a_measurement_is_defined_once_and_read_by_an_item_and_an_intent(self):
        defs = self.defs()
        criterion = resources.load_json(INTENT)["$defs"]
        for part in ("measured_on", "actual", "source"):
            with self.subTest(part):
                self.assertEqual(defs["result"]["properties"][part]["$ref"], f"#/$defs/{part}")
                self.assertEqual(criterion["criterion_result"]["properties"][part]["$ref"], f"urn:aidd:1:product-scope#/$defs/{part}")
        self.assertEqual(criterion["criterion_result"]["properties"]["decision"]["$ref"], "urn:aidd:1:product-scope#/$defs/result/properties/decision")
        self.assertEqual(defs["metric"]["properties"]["source"]["$ref"], "#/$defs/source")
        self.assertEqual(criterion["criterion"]["properties"]["metric"]["$ref"], "urn:aidd:1:product-scope#/$defs/metric")

    def test_an_item_stores_no_status_for_its_latest_result_gives_it(self):
        defs = self.defs()
        for kind in ("objective", "requirement", "product_outcome", "standing_outcome"):
            with self.subTest(kind):
                self.assertNotIn("status", defs[kind]["properties"])
                self.assertIs(defs[kind]["additionalProperties"], False)
                self.assertIn("results", defs[kind]["properties"])

    def test_each_file_names_its_approval_right_after_the_person_who_decides_it(self):
        for name, before in (("brd", "sponsor"), ("prd", "type"), ("standing_outcomes", "type"), ("intent_order", "owner")):
            with self.subTest(name):
                keys = list(self.defs()[name]["properties"])
                self.assertEqual(keys[keys.index(before) + 1 : keys.index(before) + 3], ["approved_by", "approved_at"])

    def test_the_four_types_are_the_rows_of_the_group_and_each_has_its_definition(self):
        rows = config.item_type_rows()
        names = config.types_in("product_scope")
        self.assertEqual(names, ("brd", "prd", "standing-outcomes", "intent-order"))
        schema = resources.load_json(SCOPE)
        self.assertEqual(schema["properties"]["type"]["enum"], list(names))
        for name in names:
            with self.subTest(name):
                self.assertEqual((rows[name]["form"], rows[name]["schema"]), ("typed_document", SCOPE))
                self.assertEqual(schema["$defs"][name.replace("-", "_")]["properties"]["type"]["const"], name)
                self.assertEqual(config.item_type_groups()["product_scope"], "the product scope")
        self.assertEqual(
            {rows[n]["files"][0]["path"] for n in names}, {"{product}/brd.md", "{product}/prd.md", "{product}/outcomes.md", "{product}/intents/order.md"}
        )

    def test_a_folder_placeholder_of_a_row_is_one_the_registry_says_what_it_stands_for(self):
        properties = resources.load_json("item-types.schema.json")["$defs"]["type"]["properties"]
        paths = {"folder": lambda row: [row.get("folder", "")], "files": lambda row: [f["path"] for f in row.get("files", [])]}
        for key, expected in (("folder", {"{specs}", "{proposals}", "{product}"}), ("files", {"{docs}", "{product}"})):
            with self.subTest(key):
                placeholders = {p for row in config.item_type_rows().values() for path in paths[key](row) for p in re.findall(r"\{[a-z]+\}", path)}
                self.assertEqual(placeholders, expected)
                for placeholder in placeholders:
                    self.assertIn(f"`{placeholder}`", properties[key]["description"])


class TheStepCodes(unittest.TestCase):
    def test_each_new_code_says_who_takes_it_and_stands_where_its_object_moves(self):
        who = {"product_scope.approve": "person", "product_scope.stalled": "agent", "product_scope.review_due": "person", "intent.result_due": "agent"}
        codes = list(steps.STEP_CODES)
        for code, taker in who.items():
            with self.subTest(code):
                self.assertEqual(steps.STEP_CODES[code], taker)
                self.assertTrue(steps.STEP_MEANINGS[code].strip())
                self.assertIn(code, steps.STEP_WORDS)
        self.assertEqual(codes.index("product_scope.approve") + 1, codes.index("product_scope.stalled"))
        self.assertEqual(codes.index("product_scope.stalled") + 1, codes.index("product_scope.review_due"))
        self.assertEqual(codes.index("product_scope.review_due") + 1, codes.index("intent.approve"))
        self.assertEqual(codes.index("intent.close") + 1, codes.index("intent.result_due"))

    def test_the_words_a_person_types_name_the_item_and_hold_no_text_of_the_repository(self):
        self.assertEqual(steps.step_words("product_scope.stalled", "Outcome-2"), "Propose the Intents that serve Outcome-2, then wait for my answer")
        self.assertEqual(steps.step_words("product_scope.stalled", "not an id; rm -rf"), "")
        self.assertEqual(
            steps.step_words("intent.result_due", "INTENT-4"),
            "Draft each due criterion's result on INTENT-4 from its success criteria, then wait for my answer",
        )
        self.assertIn("criterion's `result`", steps.STEP_MEANINGS["intent.result_due"])
        self.assertIn("success criteria", steps.STEP_MEANINGS["intent.result_due"])
        self.assertEqual(steps.step_words("intent.result_due", "x y"), "")
        for code in ("product_scope.approve", "product_scope.review_due"):
            self.assertTrue(steps.step_words(code, "anything"), code)


class TheProductDir(unittest.TestCase):
    def test_a_folder_inside_the_repository_is_one_and_the_top_is_not(self):
        for value, valid in (
            ("product", True),
            ("docs/product", True),
            ("./custom/", True),  # a leading `./` is read away, as for every folder setting
            (".", False),
            ("./", False),
            ("", False),
            ("/abs", False),
            ("../up", False),
            ("a/../b", False),
            ("a*", False),
            ("a?", False),
            (3, False),
        ):
            with self.subTest(product_dir=value):
                found = problems({"aidd_version": "1.0.0", "profile": "solo", "product_dir": value}, "config.schema.json")
                self.assertEqual(not found, valid, found)

    def test_the_setting_is_read_as_a_folder_and_defaults_to_product(self):
        self.assertEqual(config.EMPTY.product_dir, "product")
        for text, folder in (
            ("product_dir: custom\n", "custom"),
            ("product_dir: ./custom/\n", "custom"),
            ("product_dir: docs/product/\n", "docs/product"),
            ("specs_dir: product\n", "product"),
        ):
            with self.subTest(text=text):
                cfg = config.load_text(f'aidd_version: "1.0.0"\nprofile: solo\n{text}')
                self.assertEqual(cfg.product_dir, folder if "product_dir" in text else "product")

    def test_the_other_folder_settings_say_the_same_of_the_top(self):
        for key in ("specs_dir", "proposals_dir", "product_dir"):
            with self.subTest(key):
                found = problems({"aidd_version": "1.0.0", "profile": "solo", key: "."}, "config.schema.json")
                self.assertTrue(found)
        self.assertTrue((Path(ROOT) / "docs" / "CONFIG.md").read_text(encoding="utf-8").count("| `product_dir` |") == 1)


if __name__ == "__main__":
    unittest.main()
