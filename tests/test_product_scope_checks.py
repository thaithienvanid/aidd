"""What `aidd validate` says of the product scope and the Intents that serve it: each `serves` resolves to an item of the right
type that is not retired, an id once approved is kept, one shape holds, a placeholder is never approved, an approver is a
person, the intent order names Intents, and three counts and dates say an Intent may be several goals. A repository with no
product scope hears nothing new, and a file of another tool in the product folder is left alone.

A finding carries no code of its own yet, so a row names the facts it must state: the path, the ids, the field, the number,
and the status or type word the finding turns on."""

import datetime as dt
import itertools
import re
import unittest
from unittest import mock

from product_scope_fixtures import (
    CONFIG,
    CONTINUE,
    MET,
    OTHER,
    PERSON,
    RETIRED,
    TODAY,
    ScopeCase,
    brd,
    intent,
    objective,
    order,
    outcome,
    prd,
    requirement,
    smallest_brd,
    standing,
    standing_outcomes,
    text,
)

from aidd import workitems
from aidd.kernel import documents, git
from aidd.workitems import approval_commits, intent_paths, intents, product_checks, product_scope, spec_file

BRD_AND_PRD = {"product/brd.md": brd(), "product/prd.md": prd()}
PRD_ONLY = {"product/prd.md": prd([outcome(serves="Objective-1")], objectives=[objective()])}
BRD_ONLY = {"product/brd.md": brd()}
STANDING_ONLY = {"product/outcomes.md": standing_outcomes()}
NO_SCOPE: dict = {}


class WhatAnIntentServes(ScopeCase):
    """Rows: the shape of the product scope, what the Intent serves, and the facts its one finding states (`()` for none)."""

    CASES = [
        # serves resolves in each shape
        ("a BRD and a PRD: a product outcome", BRD_AND_PRD, "Outcome-1", ()),
        ("a PRD only: a product outcome", PRD_ONLY, "Outcome-1", ()),
        ("a BRD only: a requirement", BRD_ONLY, "Requirement-1", ()),
        ("standing outcomes only: a standing outcome", STANDING_ONLY, "Outcome-1", ()),
        # the wrong type, and an id nobody holds
        ("a BRD and a PRD: a requirement, which the outcome serves", BRD_AND_PRD, "Requirement-1", ("Requirement-1", "requirement", "outcome")),
        ("a PRD only: a requirement no BRD holds", PRD_ONLY, "Requirement-1", ("Requirement-1",)),
        ("a BRD only: an outcome no PRD holds", BRD_ONLY, "Outcome-1", ("Outcome-1",)),
        ("a number that does not exist", BRD_AND_PRD, "Outcome-9", ("Outcome-9",)),
        # no product scope at all
        ("no product scope: an id that holds nowhere", NO_SCOPE, "Outcome-1", ("Outcome-1",)),
        ("no product scope: no serves, as before", NO_SCOPE, None, ()),
        # an Intent owes a serves once a product scope exists
        ("a BRD and a PRD: no serves", BRD_AND_PRD, None, ("INTENT-1", "nothing")),
        ("standing outcomes only: no serves", STANDING_ONLY, None, ("INTENT-1", "nothing")),
    ]

    def test_each_row_says_what_it_should(self):
        for name, files, serves, facts in self.CASES:
            with self.subTest(name):
                self.fresh()
                for rel, data in files.items():
                    self.write(rel, data)
                self.write("product/intents/INTENT-1.md", intent(serves=serves))
                errors, _, _ = self.check()
                mine = [e for e in errors if "INTENT-1" in e]
                self.assertEqual(len(self.said(mine, *facts)) if facts else len(mine), 1 if facts else 0, mine)

    def test_a_retired_item_is_an_error_and_a_met_one_a_note(self):
        for name, result, level in (("retired", RETIRED, "error"), ("met", MET, "note"), ("still going", CONTINUE, "none")):
            with self.subTest(name):
                self.fresh()
                self.write("product/outcomes.md", standing_outcomes([standing(results=[result])]))
                self.write("product/intents/INTENT-1.md", intent(serves="Outcome-1"))
                errors, _, notes = self.check()
                self.assertEqual(len(self.said(errors, "INTENT-1", "Outcome-1", "retired")), 1 if level == "error" else 0, errors)
                self.assertEqual(len(self.said(notes, "INTENT-1", "Outcome-1", "met")), 1 if level == "note" else 0, notes)

    def test_the_candidates_a_missing_serves_names_are_of_the_type_it_may_serve(self):
        for name, files, want, never in (
            ("a BRD and a PRD", BRD_AND_PRD, "Outcome-1", "Requirement-1"),
            ("a BRD only", BRD_ONLY, "Requirement-1", "Outcome-"),
            ("standing outcomes", STANDING_ONLY, "Outcome-1", "Requirement-"),
        ):
            with self.subTest(name):
                self.fresh()
                for rel, data in files.items():
                    self.write(rel, data)
                self.write("product/intents/INTENT-1.md", intent())
                errors, _, _ = self.check()
                (found,) = [e for e in errors if "INTENT-1" in e]
                self.assertIn(want, found)
                self.assertNotIn(never, found)

    def test_the_latest_result_decides_the_status(self):
        later = {"measured_on": "2027-01-09", "actual": "50%", "source": "support report", "decision": "continue"}
        for name, results, retired in (
            ("retired, then taken up again", [RETIRED, later], False),
            ("taken up, then retired", [{**later, "measured_on": "2027-01-01"}, RETIRED], True),
            ("two on one day: the last written wins", [later | {"measured_on": "2027-01-02"}, RETIRED], True),
            ("two on one day, retired first", [RETIRED, later | {"measured_on": "2027-01-02"}], False),
        ):
            with self.subTest(name):
                self.assertEqual(product_scope.result_status(results) == "retired", retired)

    def test_a_closed_intent_keeps_only_the_check_of_an_id_nobody_holds(self):
        for name, serves, want in (
            ("no serves", None, 0),
            ("a retired item", "Outcome-1", 0),
            ("an id nobody holds", "Outcome-9", 1),
        ):
            with self.subTest(name):
                self.fresh()
                self.write("product/outcomes.md", standing_outcomes([standing(results=[RETIRED])]))
                self.write("product/intents/INTENT-1.md", intent(serves=serves, status="done"))
                errors, _, notes = self.check()
                self.assertEqual(len([e for e in errors if "INTENT-1" in e]), want, errors)
                self.assertEqual([n for n in notes if "INTENT-1" in n], [])

    def test_serves_with_covers_is_allowed_and_the_product_scope_still_checks_it(self):
        for serves, want in (("Outcome-1", 0), ("Outcome-9", 1)):
            with self.subTest(serves):
                self.fresh()
                self.write("product/outcomes.md", standing_outcomes())
                self.write("product/intents/INTENT-1.md", intent(serves=serves, covers=["NEED-1"]))
                errors, _, _ = self.check()
                self.assertEqual(len([e for e in errors if "INTENT-1" in e]), want, errors)
                self.assertEqual([e for e in errors if "covers" in e], [])

    def test_an_unreadable_product_file_does_not_make_every_serves_a_mistake(self):
        self.write("product/brd.md", brd())
        self.write("product/prd.md", "---\ntype: prd\noutcomes: not a list\n---\n")
        self.write("product/intents/INTENT-1.md", intent(serves="Outcome-1"))
        errors, _, _ = self.check()
        self.assertEqual(len(self.said(errors, "prd.md")), 1, errors)
        self.assertEqual(self.said(errors, "INTENT-1", "Outcome-1"), [])

    def test_a_product_scope_type_in_the_wrong_file_is_named(self):
        self.write("product/prd.md", brd())
        errors, _, _ = self.check()
        self.assertEqual(len(self.said(errors, "product/prd.md", "type", "prd")), 1, errors)


class AFileOfAnotherTool(ScopeCase):
    """A file in the product folder whose front matter names no type of the product scope is not part of it: it is left alone, and
    the repository answers as it did without it, in `aidd validate` and in `aidd status`."""

    FOREIGN = {
        "front matter of another tool in prd.md": {"product/prd.md": "---\ntitle: Pricing page\ntype: page\n---\n\nWords.\n"},
        "no front matter in brd.md": {"product/brd.md": "# Business requirements\n\nWords.\n"},
        "another type in the order file": {"product/intents/order.md": "---\ntype: page\n---\n\nWords.\n"},
        "front matter with no type in outcomes.md": {"product/outcomes.md": "---\ntitle: Outcomes\n---\n"},
        "all of them": {
            "product/prd.md": "---\ntype: post\n---\n",
            "product/brd.md": "plain words\n",
            "product/intents/order.md": "---\ntype: page\n---\n",
            "product/outcomes.md": "---\ntitle: x\n---\n",
        },
    }

    def test_validate_and_status_answer_as_they_did_without_the_files(self):
        base_errors, base_warnings, base_notes = [], [], []
        self.fresh()
        self.write("product/intents/INTENT-1.md", intent())
        base = self.repository_check()
        for name, files in self.FOREIGN.items():
            with self.subTest(name):
                self.fresh()
                self.write("product/intents/INTENT-1.md", intent())
                for rel, content in files.items():
                    self.write(rel, content)
                self.assertEqual(self.repository_check(), base)
                answer = workitems.open_work(self.root, self.config())
                self.assertNotIn("product_scope", answer)
                self.assertEqual([i["id"] for i in answer["items"]], ["INTENT-1"])
                self.assertEqual(product_scope.read(self.root, "product").files, {})
        self.assertEqual((base_errors, base_warnings, base_notes), ([], [], []))

    def test_a_real_file_beside_a_foreign_one_is_still_read(self):
        self.write("product/prd.md", prd([outcome(serves="Requirement-9")]))
        self.write("product/brd.md", "# Not the BRD\n")
        errors, _, _ = self.check()
        self.assertEqual(len(self.said(errors, "product/prd.md", "Requirement-9")), 1, errors)


class WhatTheItemsServe(ScopeCase):
    CASES = [
        ("a requirement serves an objective", {"product/brd.md": brd()}, ()),
        (
            "a requirement serves an objective that is not there",
            {"product/brd.md": brd(requirements=[requirement(serves="Objective-7")])},
            ("Requirement-1", "Objective-7"),
        ),
        (
            "a requirement serves a retired objective",
            {"product/brd.md": brd(objectives=[objective(results=[RETIRED])])},
            ("Requirement-1", "Objective-1", "retired"),
        ),
        ("an outcome beside a BRD serves a requirement", BRD_AND_PRD, ()),
        ("an outcome beside a BRD serves nothing", {**BRD_ONLY, "product/prd.md": prd([outcome(serves=None)])}, ("Outcome-1", "BRD")),
        (
            "an outcome beside a BRD serves an objective, not a requirement",
            {**BRD_ONLY, "product/prd.md": prd([outcome(serves="Objective-1")])},
            ("Outcome-1", "Objective-1", "objective", "requirement"),
        ),
        (
            "an outcome serves a retired requirement",
            {"product/brd.md": brd(requirements=[requirement(results=[RETIRED])]), "product/prd.md": prd()},
            ("Outcome-1", "Requirement-1", "retired"),
        ),
        ("an outcome with no BRD may serve nothing", {"product/prd.md": prd([outcome(serves=None)])}, ()),
        ("an outcome with no BRD serves an objective of the PRD", PRD_ONLY, ()),
        ("an outcome with no BRD serves a requirement no BRD holds", {"product/prd.md": prd([outcome()])}, ("Outcome-1", "Requirement-1")),
    ]

    def test_each_row_says_what_it_should(self):
        for name, files, facts in self.CASES:
            with self.subTest(name):
                self.fresh()
                for rel, data in files.items():
                    self.write(rel, data)
                errors, _, _ = self.check()
                self.assertEqual(len(self.said(errors, *facts)) if facts else len(errors), 1 if facts else 0, errors)

    def test_one_shape_holds(self):
        both = {**BRD_AND_PRD, "product/outcomes.md": standing_outcomes([standing(5)])}
        cases = [
            ("standing outcomes beside a PRD", {**PRD_ONLY, "product/outcomes.md": standing_outcomes([standing(5)])}, ("outcomes.md", "prd.md")),
            ("standing outcomes beside a BRD", {**BRD_ONLY, "product/outcomes.md": standing_outcomes([standing(5)])}, ("outcomes.md", "brd.md")),
            ("standing outcomes beside both", both, ("outcomes.md", "brd.md", "prd.md")),
            ("objectives in both a BRD and a PRD", {**BRD_ONLY, "product/prd.md": prd(objectives=[objective(2)])}, ("objectives", "brd.md", "prd.md")),
            ("a BRD and a PRD that split the objectives", BRD_AND_PRD, ()),
        ]
        for name, files, facts in cases:
            with self.subTest(name):
                self.fresh()
                for rel, data in files.items():
                    self.write(rel, data)
                errors, _, _ = self.check()
                self.assertEqual(len(self.said(errors, *facts)) if facts else len(errors), 1 if facts else 0, errors)

    def test_an_id_is_held_once(self):
        cases = [
            ("two files", {"product/brd.md": brd(), "product/prd.md": prd([outcome(1), outcome(1)])}, 1),
            ("one file", {"product/prd.md": prd([outcome(1, serves=None), outcome(1, serves=None)])}, 1),
            ("three of the same", {"product/prd.md": prd([outcome(2, serves=None)] * 3)}, 2),
            ("each id once", {"product/prd.md": prd([outcome(1, serves=None), outcome(2, serves=None)])}, 0),
        ]
        for name, files, want in cases:
            with self.subTest(name):
                self.fresh()
                for rel, data in files.items():
                    self.write(rel, data)
                errors, _, _ = self.check()
                self.assertEqual(len(errors), want, errors)


class WhereRequirementsLive(ScopeCase):
    """A requirement lives in the one product scope file the product has: the BRD, else the PRD, else the standing outcomes. It
    serves an objective where the product scope holds objectives. Rows: the files, then the facts each expected error states."""

    SMALL = {"product/brd.md": smallest_brd()}
    CASES = [
        # the smallest BRD, and where requirements may live
        ("a BRD of a sponsor and requirements", SMALL, ()),
        ("a BRD with objectives, each requirement serving one", {"product/brd.md": brd()}, ()),
        ("a PRD with requirements and no BRD", {"product/prd.md": prd([outcome(serves=None)], requirements=[requirement(serves=None)])}, ()),
        ("standing outcomes with requirements", {"product/outcomes.md": standing_outcomes(requirements=[requirement(serves=None)])}, ()),
        (
            "a PRD with objectives, its requirement serving one",
            {"product/prd.md": prd([outcome(serves="Objective-1")], objectives=[objective()], requirements=[requirement()])},
            (),
        ),
        ("no product scope at all", {}, ()),
        # a requirement serves an objective once the product scope holds objectives
        (
            "a BRD with objectives and a requirement that serves nothing",
            {"product/brd.md": brd(requirements=[requirement(serves=None)])},
            (("product/brd.md", "Requirement-1", "Objective"),),
        ),
        (
            "a PRD with objectives and a requirement that serves nothing",
            {"product/prd.md": prd([outcome(serves=None)], objectives=[objective()], requirements=[requirement(serves=None)])},
            (("product/prd.md", "Requirement-1", "Objective"),),
        ),
        # one file holds the requirements
        (
            "requirements in a BRD and in a PRD",
            {**SMALL, "product/prd.md": prd([outcome(serves="Requirement-1")], requirements=[requirement(2, serves=None)])},
            (("requirements", "product/brd.md", "product/prd.md"),),
        ),
        (
            "a BRD with objectives, and a PRD with requirements",
            {"product/brd.md": brd(), "product/prd.md": prd([outcome(serves="Requirement-1")], requirements=[requirement(2, "Objective-1")])},
            (("requirements", "product/brd.md", "product/prd.md"),),
        ),
        (
            "a BRD with objectives, and a PRD whose requirement serves nothing: the move is the one step",
            {"product/brd.md": brd(), "product/prd.md": prd([outcome(serves="Requirement-1")], requirements=[requirement(2, serves=None)])},
            (("requirements", "product/brd.md", "product/prd.md"),),
        ),
        (
            "a BRD that holds objectives and does not read: its own error is the only one",
            {
                "product/brd.md": {**brd(), "requirements": [{"title": "no id"}]},
                "product/prd.md": prd([outcome(serves=None)], requirements=[requirement(2, serves=None)]),
            },
            (("product/brd.md", "missing required field 'id'"),),
        ),
        (
            "objectives in a PRD, and a BRD that holds none: they belong in the BRD, and the requirement then serves one",
            {**SMALL, "product/prd.md": prd([outcome(serves="Requirement-1")], objectives=[objective(2)])},
            (("product/prd.md", "objectives", "move them into product/brd.md"), ("product/brd.md", "Requirement-1", "serves nothing")),
        ),
        (
            "requirements in a BRD and in standing outcomes, which the shape error names too",
            {**SMALL, "product/outcomes.md": standing_outcomes(requirements=[requirement(2, serves=None)])},
            (("requirements", "product/brd.md", "product/outcomes.md"), ("standing outcomes", "product/brd.md")),
        ),
        (
            "requirements in a PRD and in standing outcomes, which the shape error names too",
            {
                "product/prd.md": prd([outcome(serves=None)], requirements=[requirement(serves=None)]),
                "product/outcomes.md": standing_outcomes([standing(2)], requirements=[requirement(2, serves=None)]),
            },
            (("requirements", "product/prd.md", "product/outcomes.md"), ("standing outcomes", "product/prd.md")),
        ),
        ("a BRD, and a PRD with no requirements", {**SMALL, "product/prd.md": prd([outcome(serves="Requirement-1")])}, ()),
    ]

    def test_each_row_says_what_it_should(self):
        for name, files, facts in self.CASES:
            with self.subTest(name):
                self.fresh()
                for rel, data in files.items():
                    self.write(rel, data)
                errors, _, _ = self.check()
                self.assertEqual(len(errors), len(facts), errors)
                for words in facts:
                    self.assertEqual(len(self.said(errors, *words)), 1, (words, errors))

    def test_every_shape_that_held_before_holds_now(self):
        """Over every choice of a BRD, a PRD, and standing outcomes that holds no requirement but a BRD's, each serving an
        objective, every finding is the one before: none, unless the standing outcomes stand beside another file, and then
        that error alone. A new warning or note fails it too."""
        for with_brd, with_prd, with_standing in itertools.product((False, True), repeat=3):
            if not (with_brd or with_prd or with_standing):
                continue
            with self.subTest(brd=with_brd, prd=with_prd, standing=with_standing):
                self.fresh()
                if with_brd:
                    self.write("product/brd.md", brd())
                if with_prd:
                    self.write("product/prd.md", prd() if with_brd else PRD_ONLY["product/prd.md"])
                if with_standing:
                    self.write("product/outcomes.md", standing_outcomes([standing(5)]))
                errors, warnings, notes = self.check()
                self.assertEqual((warnings, notes), ([], []))
                if with_standing and (with_brd or with_prd):
                    self.assertEqual(len(errors), 1, errors)
                    self.assertIn("standing outcomes stand for a product with neither", errors[0])
                else:
                    self.assertEqual(errors, [])

    def test_the_move_is_named_before_what_the_move_settles(self):
        self.write("product/brd.md", brd())
        self.write("product/prd.md", prd([outcome(serves="Requirement-1")], objectives=[objective(2)], requirements=[requirement(2, serves=None)]))
        errors, _, _ = self.check()
        self.assertIn("requirements are in", errors[0])
        self.assertIn("objectives", errors[1])

    def test_the_error_of_two_files_names_the_step_that_works(self):
        for rel, data in (
            ("product/prd.md", prd([outcome(serves="Requirement-1")], requirements=[requirement(2, serves=None)])),
            ("product/outcomes.md", standing_outcomes(requirements=[requirement(2, serves=None)])),
        ):
            with self.subTest(rel):
                self.fresh()
                self.write("product/brd.md", smallest_brd())
                self.write(rel, data)
                (found,) = self.said(self.check()[0], "requirements")
                self.assertIn("move", found)
                self.assertIn("product/brd.md", found.split("move", 1)[1], "it says which file the requirements go to")


class WhatStaysOnceApproved(ScopeCase):
    def test_an_id_the_last_approval_held_is_gone(self):
        for name, now, gone in (
            ("an item removed", brd(requirements=[requirement(2)]), ["Requirement-1"]),
            ("every item kept", brd(), []),
            ("an item added", brd(requirements=[requirement(), requirement(2)]), []),
            ("an item retired, never removed", brd(requirements=[requirement(results=[RETIRED])]), []),
        ):
            with self.subTest(name):
                self.fresh()
                before = self.approve("product/brd.md", brd())
                self.write("product/brd.md", {**now, "approved_by": before["approved_by"], "approved_at": before["approved_at"]})
                errors, _, _ = self.check()
                self.assertEqual([e.split(" ")[1] for e in self.said(errors, "gone")], gone, errors)

    def test_removing_the_stamps_with_the_item_hides_nothing(self):
        for name, stamps in (
            ("the stamps removed", {}),
            ("the time moved, with no commit that records it", {"approved_by": PERSON, "approved_at": "2027-01-14T09:00:00Z"}),
            ("another person named, with no commit that records it", {"approved_by": OTHER, "approved_at": "2027-01-10T09:00:00Z"}),
        ):
            with self.subTest(name):
                self.fresh()
                self.approve("product/brd.md", brd())
                self.write("product/brd.md", {**brd(requirements=[requirement(2)]), **stamps})
                errors, _, _ = self.check()
                self.assertEqual([e.split(" ")[1] for e in self.said(errors, "gone")], ["Requirement-1"], errors)

    def test_a_later_approval_commit_is_the_last_one(self):
        """An id removed in an approved change is gone from the last approval on: it is lost when it leaves the next one."""
        self.approve("product/brd.md", brd(requirements=[requirement(), requirement(2)]), at="2027-01-05T09:00:00Z")
        self.approve("product/brd.md", brd(requirements=[requirement(2)]), at="2027-01-10T09:00:00Z")
        self.write("product/brd.md", {**brd(requirements=[requirement(2)]), "approved_by": PERSON, "approved_at": "2027-01-10T09:00:00Z"})
        errors, _, _ = self.check()
        self.assertEqual(self.said(errors, "gone"), [], "the id the last approval no longer held is not gone from it")

    def test_an_id_that_moved_to_another_file_is_not_gone(self):
        self.approve("product/prd.md", prd([outcome(serves=None)], objectives=[objective()]))
        self.write("product/brd.md", brd())
        self.approve("product/prd.md", prd([outcome(serves="Requirement-1")]))
        errors, _, _ = self.check()
        self.assertEqual(self.said(errors, "gone"), [])

    def test_a_file_never_approved_has_nothing_to_lose(self):
        self.write("product/brd.md", brd())
        self.commit()
        self.write("product/brd.md", brd(requirements=[requirement(2)]))
        errors, warnings, _ = self.check()
        self.assertEqual(self.said(errors, "gone"), [])
        self.assertEqual(self.said(warnings, "approved"), [])

    def test_an_approval_no_commit_records_stands_for_nothing(self):
        before = brd() | {"approved_by": PERSON, "approved_at": "2027-01-10T09:00:00Z"}
        self.write("product/brd.md", before)
        self.commit("approve it, with no trailer")
        self.write("product/brd.md", {**before, "requirements": [requirement(2)]})
        errors, warnings, _ = self.check()
        self.assertEqual(self.said(errors, "gone"), [], "no approval stands, so none is lost")
        self.assertEqual(len(self.said(warnings, "Approved-by")), 1, warnings)

    def test_only_a_persons_own_approved_by_and_approves_lines_record_an_approval(self):
        """The commit of the approval holds the person's `Approved-by` line and `Approves: <the file's path>`: one without the other,
        another person's, an Intent's lines, or a delegate's yes beside them hold nothing. (Changed on purpose: `Approved-by` alone held.)"""
        delegated = ("Decided-by: agent:claude-code/claude-opus-5-5", f"On-behalf-of: {PERSON}", "Delegation: " + "a" * 40)
        rel = "product/brd.md"
        for name, trailers, stands in (
            ("the person's Approved-by and the file's path", (f"Approved-by: {PERSON}", f"Approves: {rel}"), True),
            ("the person's Approved-by alone", (f"Approved-by: {PERSON}",), False),
            ("the path alone", (f"Approves: {rel}",), False),
            ("an Intent's Agreed-by", (f"Agreed-by: {PERSON}",), False),
            ("an Intent's lines", (f"Approved-by: {PERSON}", "Approves: INTENT-1"), False),
            ("another file's path", (f"Approved-by: {PERSON}", "Approves: product/prd.md"), False),
            ("another person's Approved-by", (f"Approved-by: {OTHER}", f"Approves: {rel}"), False),
            ("a delegate's yes beside them", (f"Approved-by: {PERSON}", f"Approves: {rel}", *delegated), False),
            ("no trailer", (), False),
        ):
            with self.subTest(name):
                self.fresh()
                approved = {**brd(), "approved_by": PERSON, "approved_at": "2027-01-10T09:00:00Z"}
                self.write(rel, brd())
                self.commit("write")
                self.write(rel, approved)
                self.commit("approve", *trailers)
                self.write(rel, {**approved, "requirements": [requirement(2)]})
                errors, warnings, _ = self.check()
                self.assertEqual(len(self.said(errors, "gone")), 1 if stands else 0, errors)
                self.assertEqual(len(self.said(warnings, "Approved-by")), 0 if stands else 1, warnings)

    def test_a_commit_that_creates_the_file_with_its_approval_holds_nothing(self):
        """Changed on purpose: the one commit that wrote the file and its approval, with both lines, held. Now the approval is a change
        of its own, so no approval stands, none is lost, and the warning says so."""
        rel = "product/brd.md"
        approved = {**brd(), "approved_by": PERSON, "approved_at": "2027-01-10T09:00:00Z"}
        self.write(rel, approved)
        self.commit("write and approve", f"Approved-by: {PERSON}", f"Approves: {rel}")
        self.write(rel, {**approved, "requirements": [requirement(2)]})
        errors, warnings, _ = self.check()
        self.assertEqual(self.said(errors, "gone"), [])
        self.assertEqual(len(self.said(warnings, "Approved-by")), 1, warnings)

    def test_the_commit_names_the_same_person_in_the_file_and_in_the_trailer(self):
        data = brd()
        rel = "product/brd.md"
        # the file said one person, and the trailer another
        approved = self.hold(rel, data, {**data, "approved_by": PERSON, "approved_at": "2027-01-10T09:00:00Z"}, rel, OTHER)
        self.write(rel, {**approved, "approved_by": OTHER, "requirements": [requirement(2)]})  # the file now says the trailer's
        errors, warnings, _ = self.check()
        self.assertEqual(self.said(errors, "gone"), [])
        self.assertEqual(len(self.said(warnings, "Approved-by")), 1, warnings)

    def test_a_change_since_the_approval_asks_for_it_again(self):
        approved = self.approve("product/prd.md", prd([outcome(serves=None)]))
        for name, now, want in (
            ("as approved", approved, ""),
            ("an item added", {**approved, "outcomes": [outcome(serves=None), outcome(2, serves=None)]}, "Outcome-2 added"),
            ("a target changed", {**approved, "outcomes": [{**outcome(serves=None), "title": "Another"}]}, "Outcome-1 changed"),
            ("another key", {**approved, "review_due": "2027-06-01"}, "other text changed"),
        ):
            with self.subTest(name):
                self.write("product/prd.md", now)
                _, warnings, _ = self.check()
                self.assertEqual(len(self.said(warnings, "product/prd.md")), 1 if want else 0, warnings)
                if want:
                    self.assertEqual(len(self.said(warnings, want)), 1, warnings)

    def test_a_removed_item_is_said_once(self):
        approved = self.approve("product/brd.md", brd(requirements=[requirement(), requirement(2)]))
        self.write("product/brd.md", {**approved, "requirements": [requirement(2)]})
        errors, warnings, _ = self.check()
        self.assertEqual(len(self.said(errors, "Requirement-1", "gone")), 1, errors)
        self.assertEqual(self.said(warnings, "Requirement-1"), [], "a removal is the error of a gone id, and no warning besides")

    def test_the_body_is_part_of_what_was_approved(self):
        approved = self.approve("product/prd.md", prd([outcome(serves=None)]))
        self.write("product/prd.md", text(approved, "\n## Notes\n\nAnother sentence.\n"))
        _, warnings, _ = self.check()
        self.assertEqual(len(self.said(warnings, "product/prd.md", "other text")), 1, warnings)

    def test_the_order_is_part_of_what_was_approved(self):
        approved = self.approve("product/intents/order.md", order(["INTENT-1", "INTENT-2"]))
        self.write("product/intents/order.md", {**approved, "order": ["INTENT-2", "INTENT-1"]})
        _, warnings, _ = self.check()
        self.assertEqual(len(self.said(warnings, "order.md", "order")), 1, warnings)


class WhatIsNeverApproved(ScopeCase):
    def test_a_placeholder_in_the_front_matter_is_an_error_naming_its_field(self):
        cases = [
            ("a target", prd([{**outcome(serves=None), "metric": {**outcome()["metric"], "target": "TODO: the value"}}]), "outcomes[0].metric.target"),
            ("a source", prd([{**outcome(serves=None), "metric": {**outcome()["metric"], "source": "TODO"}}]), "outcomes[0].metric.source"),
            ("nothing left", prd([outcome(serves=None)]), ""),
        ]
        for name, data, field in cases:
            with self.subTest(name):
                self.fresh()
                self.write("product/prd.md", data)
                errors, warnings, _ = self.check()
                self.assertEqual(len(self.said(errors, "TODO", field)) if field else len(errors), 1 if field else 0, errors)
                self.assertEqual(warnings, [], "one fact, once: no generic placeholder warning beside the error")

    def test_an_order_placeholder_is_a_reminder_until_a_product_scope_starts_or_the_file_is_approved(self):
        owner = "TODO: name the person who orders the Intents"
        for name, files, approved, level in (
            ("an upgraded repository: the order alone", {}, False, "warning"),
            ("a PRD exists", {"product/prd.md": prd([outcome(serves=None)])}, False, "error"),
            ("a BRD exists", {"product/brd.md": brd()}, False, "error"),
            ("standing outcomes exist", STANDING_ONLY, False, "error"),
            ("the order was approved", {}, True, "error"),
            ("a foreign file of the same name", {"product/prd.md": "---\ntype: page\n---\n"}, False, "warning"),
        ):
            with self.subTest(name):
                self.fresh()
                for rel, data in files.items():
                    self.write(rel, data)
                self.write(
                    "product/intents/order.md",
                    order([], owner=owner, **({"approved_by": PERSON, "approved_at": "2027-01-10T09:00:00Z"} if approved else {})),
                )
                errors, warnings, _ = self.check()
                found = self.said(errors if level == "error" else warnings, "order.md", "owner", "TODO")
                self.assertEqual(len(found), 1, (errors, warnings))
                self.assertEqual(self.said(warnings if level == "error" else errors, "order.md", "TODO"), [], "said once, at one level")

    def test_an_upgraded_repository_stays_green_until_a_product_scope_starts(self):
        self.write("product/intents/INTENT-1.md", intent())
        self.write("product/intents/order.md", order(["INTENT-1"], owner="TODO: name the person who orders the Intents"))
        errors, warnings, _ = self.repository_check()
        self.assertEqual(errors, [])
        self.assertEqual(len(self.said(warnings, "order.md", "owner")), 1, warnings)

    def test_many_placeholders_are_one_error_that_counts_them(self):
        data = prd([{**outcome(n, serves=None), "title": "TODO"} for n in range(1, 9)])
        self.write("product/prd.md", data)
        errors, _, _ = self.check()
        self.assertEqual(len(self.said(errors, "8 fields", "and 3 more")), 1, errors)

    def test_a_placeholder_in_the_prose_is_a_warning_only(self):
        self.write("product/prd.md", text(prd([outcome(serves=None)]), "\n## Users\n\nTODO: who uses it.\n"))
        errors, warnings, _ = self.check()
        self.assertEqual(errors, [])
        self.assertEqual(len(self.said(warnings, "product/prd.md", "TODO")), 1, warnings)

    def test_a_fresh_template_names_only_what_a_person_decides(self):
        for item_type, rel in (("brd", "brd.md"), ("prd", "prd.md"), ("standing-outcomes", "outcomes.md")):
            with self.subTest(item_type):
                self.fresh()
                workitems.new_product_file(self.root, item_type=item_type)
                errors, _, _ = self.check()
                self.assertTrue(self.said(errors, f"product/{rel}", "TODO"), errors)
                self.assertTrue(all("TODO" in e for e in errors if f"product/{rel}" in e), errors)  # the field a placeholder fills has one finding


class TheSchemaErrorOfAPlaceholder(unittest.TestCase):
    PATH = "product/prd.md"

    def test_only_the_errors_of_a_field_that_holds_a_placeholder_are_dropped(self):
        data = {"type": "prd", "outcomes": [{"id": "Outcome-1", "serves": "TODO: a requirement", "title": "A title"}]}
        found = [
            f"{self.PATH}: $.outcomes[0].serves: must match exactly one allowed shape (matched 0)",
            f"{self.PATH}: $.outcomes[0].metric: is required",
            f"{self.PATH}: $.outcomes[0].serves2: another field",
            "product/brd.md: $.outcomes[0].serves: the same field of another file",
        ]
        self.assertEqual(product_checks.without_placeholder_errors(self.PATH, data, found), found[1:])
        self.assertEqual(product_checks.without_placeholder_errors(self.PATH, {"type": "prd"}, found), found)


class WhoApproves(ScopeCase):
    def test_an_agent_is_never_the_approver_the_sponsor_or_the_product_owner(self):
        agent = "agent:claude-code/claude-opus-5-5"
        cases = [
            ("approved_by", {"product/prd.md": prd([outcome(serves=None)], approved_by=agent, approved_at="2027-01-10T09:00:00Z")}, "approved_by"),
            ("the sponsor", {"product/brd.md": brd(sponsor=agent)}, "sponsor"),
            ("the product owner", {"product/intents/order.md": order([], owner=agent)}, "owner"),
            ("a person", {"product/brd.md": brd(), "product/intents/order.md": order([])}, ""),
        ]
        for name, files, field in cases:
            with self.subTest(name):
                self.fresh()
                for rel, data in files.items():
                    self.write(rel, data)
                errors, _, _ = self.check()
                self.assertEqual(len(self.said(errors, field, "agent")) if field else len(errors), 1 if field else 0, errors)

    def test_an_approver_who_is_not_the_sponsor_is_a_warning(self):
        for name, who, want in (("the sponsor", PERSON, 0), ("another person", OTHER, 1), ("the sponsor by handle case", PERSON.upper(), 0)):
            with self.subTest(name):
                self.fresh()
                self.approve("product/brd.md", brd(), who=who)
                _, warnings, _ = self.check()
                found = self.said(warnings, "approved_by", "sponsor")
                self.assertEqual(len(found), want, warnings)
                if want:
                    self.assertIn("`sponsor`", found[0], "the message names the place to say that one person holds both roles")
                    self.assertNotIn("a person may hold", found[0], "one plain sentence, with no comma splice")

    def test_an_approver_in_no_known_form_is_a_warning(self):
        self.write("product/prd.md", prd([outcome(serves=None)], approved_by="just dana", approved_at="2027-01-10T09:00:00Z"))
        errors, warnings, _ = self.check()
        self.assertEqual(self.said(errors, "approved_by"), [])
        self.assertTrue(self.said(warnings, "approved_by", "just dana", "@handle"), warnings)


class WhatTheOrderNames(ScopeCase):
    def setUp(self):
        super().setUp()
        self.write("product/prd.md", prd([outcome(serves=None)]))
        self.write("product/intents/INTENT-1.md", intent(serves="Outcome-1"))
        self.write("specs/SPEC-3.md", "---\ntype: spec\nid: SPEC-3\ntitle: A Spec\n---\n")

    def test_each_id_is_an_intent(self):
        for name, ids, want in (
            ("an Intent", ["INTENT-1"], ()),
            ("a Spec", ["SPEC-3"], ("SPEC-3",)),
            ("an id nobody holds", ["INTENT-9"], ("INTENT-9",)),
            ("an Intent and a mistake", ["INTENT-1", "SPEC-3"], ("SPEC-3",)),
            ("none yet", [], ()),
        ):
            with self.subTest(name):
                self.write("product/intents/order.md", order(ids))
                errors, _, _ = self.check()
                self.assertEqual(len(self.said(errors, "order.md", *want)) if want else len(errors), 1 if want else 0, errors)

    def test_an_id_only_another_branch_holds_gets_a_way_that_works(self):
        self.write("product/intents/order.md", order(["INTENT-9"]))
        errors, _, _ = self.check()
        (found,) = self.said(errors, "INTENT-9")
        self.assertIn("branch", found)
        self.assertNotIn("aidd new", found)

    def test_an_id_twice_is_refused(self):
        self.write("product/intents/order.md", order(["INTENT-1", "INTENT-1"]))
        errors, _, _ = self.check()
        self.assertEqual(len(self.said(errors, "order.md")), 1, errors)

    def test_an_approved_intent_left_out_is_a_warning_and_a_draft_is_not(self):
        self.write("product/intents/INTENT-2.md", intent("INTENT-2", serves="Outcome-1"))
        self.approve_intent("product/intents/INTENT-1.md", intent(serves="Outcome-1"))
        for name, ids, want in (
            ("both listed", ["INTENT-1", "INTENT-2"], 0),
            ("the approved one listed, the draft left out", ["INTENT-1"], 0),
            ("the approved one left out", ["INTENT-2"], 1),
            ("nothing listed", [], 1),
        ):
            with self.subTest(name):
                self.write("product/intents/order.md", order(ids))
                _, warnings, _ = self.check()
                self.assertEqual(len(self.said(warnings, "order.md", "INTENT-1")), want, warnings)
                self.assertEqual(self.said(warnings, "order.md", "INTENT-2"), [], "a draft is no business of the order")

    def test_a_closed_intent_still_listed_is_a_note(self):
        for status, want in (("done", 1), ("cancelled", 1), ("", 0)):
            with self.subTest(status):
                self.write("product/intents/INTENT-1.md", intent(serves="Outcome-1", **({"status": status} if status else {})))
                self.write("product/intents/order.md", order(["INTENT-1"]))
                errors, _, notes = self.check()
                self.assertEqual(len(self.said(notes, "order.md", "INTENT-1", status or "-")), want, notes)
                self.assertEqual(self.said(errors, "INTENT-1"), [])

    def test_with_no_order_file_nothing_is_said_of_one(self):
        self.approve_intent("product/intents/INTENT-1.md", intent(serves="Outcome-1"))
        errors, warnings, notes = self.check()
        self.assertEqual([f for f in (*errors, *warnings, *notes) if "order" in f], [])


class WhenAnIntentLooksLikeSeveralGoals(ScopeCase):
    def setUp(self):
        super().setUp()
        self.write("product/prd.md", prd([outcome(serves=None)]))

    def test_the_slices_it_lists_against_the_limit(self):
        for slices, want in ((1, 0), (10, 0), (11, 1), (30, 1)):
            with self.subTest(slices=slices):
                self.write("product/intents/INTENT-1.md", intent(serves="Outcome-1", phases=(slices,)))
                _, warnings, _ = self.check()
                self.assertEqual(len(self.said(warnings, "INTENT-1", f"{slices} slices", "10")), want, warnings)

    def test_the_limit_is_the_one_given(self):
        for slices, want in ((3, 0), (4, 1)):
            with self.subTest(slices=slices):
                self.write("product/intents/INTENT-1.md", intent(serves="Outcome-1", phases=(slices,)))
                _, warnings, _ = self.check(max_specs=3)
                self.assertEqual(len(self.said(warnings, "INTENT-1", f"{slices} slices", "than 3")), want, warnings)

    def test_two_phases_that_serve_something_ask_whether_each_could_ship_alone(self):
        for name, phases, serves, want in (
            ("one phase", (3,), "Outcome-1", 0),
            ("two phases", (2, 1), "Outcome-1", 1),
            ("three phases", (1, 1, 1), "Outcome-1", 1),
            ("two phases that serve nothing", (2, 1), None, 0),
        ):
            with self.subTest(name):
                self.write("product/intents/INTENT-1.md", intent(serves=serves, phases=phases))
                _, warnings, _ = self.check()
                self.assertEqual(len(self.said(warnings, "INTENT-1", f"{len(phases)} phases", "Outcome-1")), want, warnings)

    def test_the_days_open_since_the_approval_warn_from_the_review_cycle_on(self):
        approved = self.approve_intent("product/intents/INTENT-1.md", intent(serves="Outcome-1"), at="2026-12-16T09:00:00Z")
        self.assertEqual((TODAY - dt.date(2026, 12, 16)).days, 30)
        for name, today, want in (
            ("the twenty-ninth day", TODAY - dt.timedelta(days=1), 0),
            ("the thirtieth day, as long as the cycle", TODAY, 1),
            ("the thirty-first", TODAY + dt.timedelta(days=1), 1),
            ("long after", TODAY + dt.timedelta(days=90), 1),
        ):
            with self.subTest(name):
                _, warnings, _ = self.check(today)
                self.assertEqual(len(self.said(warnings, "INTENT-1", "30-day")), want, warnings)
        self.write("product/intents/order.md", order(["INTENT-1"], review_every_days=7))
        _, warnings, _ = self.check()
        self.assertEqual(len(self.said(warnings, "INTENT-1", "7-day")), 1, warnings)
        self.write("product/intents/INTENT-1.md", {**approved, "status": "done"})
        _, warnings, _ = self.check(TODAY + dt.timedelta(days=90))
        self.assertEqual(self.said(warnings, "INTENT-1", "day"), [], "a closed Intent is never open too long")

    def test_a_repository_with_no_product_scope_hears_none_of_it(self):
        self.fresh()
        self.write("product/intents/INTENT-1.md", intent(phases=(12, 3)))
        self.approve_intent("product/intents/INTENT-1.md", intent(phases=(12, 3)), at="2026-01-01T09:00:00Z")
        errors, warnings, notes = self.check()
        self.assertEqual([*errors, *warnings, *notes], [])

    def test_an_order_file_alone_is_no_product_scope(self):
        self.fresh()
        self.write("product/intents/order.md", order(["INTENT-1"], owner=PERSON))
        self.approve_intent("product/intents/INTENT-1.md", intent(phases=(12, 3)), at="2026-01-01T09:00:00Z")
        errors, warnings, notes = self.check()
        self.assertEqual([f for f in (*errors, *warnings, *notes) if "slices" in f or "phases" in f or "day" in f], [])


class TheWholeRepository(ScopeCase):
    """`aidd validate` of the repository reads the product scope, by name, beside the other work items."""

    SHAPES = {
        "a BRD and a PRD": BRD_AND_PRD,
        "a PRD only": PRD_ONLY,
        "a BRD only": BRD_ONLY,
        "standing outcomes only": STANDING_ONLY,
    }

    def test_each_shape_with_an_intent_that_serves_it_is_clean(self):
        serves = {"a BRD and a PRD": "Outcome-1", "a PRD only": "Outcome-1", "a BRD only": "Requirement-1", "standing outcomes only": "Outcome-1"}
        for name, files in self.SHAPES.items():
            with self.subTest(name):
                self.fresh()
                for rel, data in files.items():
                    self.write(rel, data)
                self.write("product/intents/INTENT-1.md", intent(serves=serves[name]))
                errors, warnings, notes = self.repository_check()
                self.assertEqual((errors, warnings, notes), ([], [], []), "a repository of this shape has no finding at all")

    def test_a_finding_of_the_product_scope_is_said_once_with_the_other_findings(self):
        self.write("product/brd.md", brd(requirements=[requirement(serves="Objective-7")]))
        self.write("product/prd.md", prd([outcome(serves=None)]))
        self.write("product/intents/order.md", order(["SPEC-3"]))
        errors, _, _ = self.repository_check()
        for facts in (("Requirement-1", "Objective-7"), ("Outcome-1", "BRD"), ("order.md", "SPEC-3")):
            self.assertEqual(len(self.said(errors, *facts)), 1, (facts, errors))

    def test_an_approved_intent_left_out_of_the_order_is_said_by_the_repository_too(self):
        self.write("product/prd.md", prd([outcome(serves=None)]))
        self.approve_intent("product/intents/INTENT-1.md", intent(serves="Outcome-1"))
        self.write("product/intents/order.md", order([]))
        _, warnings, _ = self.repository_check()
        self.assertEqual(len(self.said(warnings, "order.md", "INTENT-1")), 1, warnings)

    def test_the_limit_on_slices_is_the_configs(self):
        self.write(".aidd/config.yaml", CONFIG + "limits:\n  max_intent_specs: 3\n")
        self.write("product/prd.md", prd([outcome(serves=None)]))
        for slices, want in ((3, 0), (4, 1)):
            with self.subTest(slices=slices):
                self.write("product/intents/INTENT-1.md", intent(serves="Outcome-1", phases=(slices,)))
                _, warnings, _ = self.repository_check()
                self.assertEqual(len(self.said(warnings, "INTENT-1", f"{slices} slices", "than 3")), want, warnings)

    def test_the_product_folder_is_the_configs(self):
        self.write(".aidd/config.yaml", CONFIG + "product_dir: plan\n")
        self.write("plan/prd.md", prd([outcome(serves="Requirement-9")]))
        errors, _, _ = self.repository_check()
        self.assertEqual(len(self.said(errors, "plan/prd.md", "Requirement-9")), 1, errors)

    def test_a_repository_with_no_product_scope_says_what_it_said_before(self):
        """Exactly the findings an earlier version gave of these Intents, and nothing besides."""
        self.write("product/intents/INTENT-1.md", intent(phases=(12, 3)))
        self.write("product/intents/INTENT-2.md", intent("INTENT-2", status="done"))
        errors, warnings, notes = self.repository_check()
        self.assertEqual(errors, [])
        said = sorted((w.replace("warning: ", "").split(": ", 1)[0], w.split(": ", 1)[1][:11]) for w in warnings)
        self.assertEqual(said, [("product/intents/INTENT-2.md", "status done")])
        self.assertEqual(notes, [])

    def test_a_product_file_is_read_by_the_walk_and_by_name_without_a_second_report(self):
        self.write("product/prd.md", text(prd([outcome(serves=None)]), "\n## Users\n\nTODO: who.\n"))
        _, warnings, _ = self.repository_check()
        self.assertEqual(len(self.said(warnings, "product/prd.md", "TODO")), 1, warnings)


class AnIntentOutsideItsFolder(ScopeCase):
    """An Intent outside the Intents' folder is read as every Intent is, and no finding is said twice for it."""

    def test_one_finding_for_the_place_and_one_for_each_thing_the_product_scope_owes_it(self):
        self.write("product/outcomes.md", standing_outcomes())
        self.write("specs/INTENT-1.md", intent())
        errors, _, _ = self.repository_check()
        mine = [e for e in errors if "specs/INTENT-1.md" in e]
        self.assertEqual(len(self.said(mine, "git mv")), 1, mine)
        self.assertEqual(len(self.said(mine, "INTENT-1", "nothing")), 1, mine)
        self.assertEqual(len(mine), 2, mine)


class TheOrderFileHasOneOwnerAndOneFirstText(ScopeCase):
    def test_the_path_of_each_file_of_the_product_scope_is_one_function_s_answer(self):
        for product_dir in ("product", "plans", "./custom/", "docs/product"):
            with self.subTest(product_dir):
                self.assertEqual(workitems.product_file("intent-order", product_dir), intent_paths.product_file("intent-order", product_dir))
                self.assertTrue(workitems.product_file("intent-order", product_dir).endswith("/intents/order.md"))
        self.assertEqual(intent_paths.product_file("brd", "./custom/"), "custom/brd.md", "`{product}` is replaced, and the path normal")

    def test_aidd_new_and_the_upgrade_start_from_the_same_text(self):
        written = workitems.new_product_file(self.root, item_type="intent-order")
        self.assertEqual(written[0].read_text(encoding="utf-8"), workitems.intent_order_text(self.root, []))
        seeded = workitems.intent_order_text(self.root, ["INTENT-2", "INTENT-1"])
        data = documents.split_front_matter(seeded, "order.md")[0]
        self.assertEqual(data["order"], ["INTENT-2", "INTENT-1"])
        empty = documents.split_front_matter(workitems.intent_order_text(self.root, []), "order.md")[0]
        self.assertEqual({**data, "order": []}, empty, "only the order differs")
        self.assertIn('owner: "TODO', seeded, "a person names the product owner, never an agent")


class TheNamesAndTheConfigAreOwnedOnce(ScopeCase):
    def test_the_order_file_has_one_public_name_for_its_path(self):
        self.assertFalse(hasattr(intent_paths, "intent_order_file"))
        self.assertFalse(hasattr(workitems, "intent_order_file"))
        self.assertEqual(workitems.product_file("intent-order", "product"), "product/intents/order.md")

    def test_the_product_findings_read_the_config_they_are_given_and_load_none(self):
        from aidd import config
        from aidd.workitems import repo_reads, validation

        self.write("product/prd.md", prd([outcome(serves=None)]))
        self.write("product/intents/INTENT-1.md", intent(serves="Outcome-1", phases=(4,)))
        small = config.load_text(CONFIG + "limits:\n  max_intent_specs: 3\n")
        found, _ = workitems.check_repo(self.root, TODAY)[0], None
        with mock.patch.object(repo_reads, "config_at", side_effect=AssertionError("the config is loaded twice")):
            said = validation._product_findings(
                self.root, small, [("product/prd.md", {}), ("product/intents/INTENT-1.md", intent(serves="Outcome-1", phases=(4,)))], {}, TODAY
            )
        self.assertEqual(len(self.said(said, "INTENT-1", "4 slices", "than 3")), 1, said)
        self.assertEqual(found, [])


class TheSeededOrderIsOneIdOnEachLineInTheTemplatesOwnLineEnding(ScopeCase):
    def test_two_or_many_intents_are_one_id_on_each_line(self):
        for ids in (["INTENT-2", "INTENT-1"], [f"INTENT-{n}" for n in range(1, 13)]):
            with self.subTest(count=len(ids)):
                text = workitems.intent_order_text(self.root, ids)
                self.assertIn("order:\n" + "".join(f"  - {i}\n" for i in ids), text)

    def test_a_crlf_template_comes_out_with_one_line_ending_throughout(self):
        template = '---\r\ntype: intent-order\r\nproduct_owner: "TODO: who"\r\norder: []\r\n---\r\n\r\nWords.\r\n'
        self.write("docs/templates/intent-order.md", "")
        (self.root / "docs/templates/intent-order.md").write_bytes(template.encode())
        text = workitems.intent_order_text(self.root, ["INTENT-2", "INTENT-1"])
        self.assertIsNone(re.search(r"(?<!\r)\n", text), text)
        self.assertEqual(documents.split_front_matter(text, "order.md")[0]["order"], ["INTENT-2", "INTENT-1"])


class AFailedReadOfAFileAtACommitIsNotKept(ScopeCase):
    def test_the_next_read_asks_git_again_and_a_read_that_worked_is_kept(self):
        approval_commits.FILE_TEXTS.clear()
        with mock.patch.object(git, "show", side_effect=[None, "text", "never asked"]) as shown:
            self.assertIsNone(approval_commits.file_at("/r", "a" * 40, "f.md"))
            self.assertEqual(approval_commits.file_at("/r", "a" * 40, "f.md"), "text")
            self.assertEqual(approval_commits.file_at("/r", "a" * 40, "f.md"), "text")
        self.assertEqual(shown.call_count, 2)


class TheFileKeepsItsWarnings(unittest.TestCase):
    def test_a_warning_of_the_schema_check_stays_with_the_file_and_the_data_is_kept(self):
        data = {"type": "prd", "outcomes": []}
        with (
            mock.patch.object(spec_file, "load_object", return_value=(data, "", ["warning: product/prd.md: a thing to look at"])),
            mock.patch.object(product_scope.objects, "read_document", return_value=("---\ntype: prd\n---\n", "")),
            mock.patch.object(product_scope.os.path, "lexists", return_value=True),
        ):
            found = product_scope.read_file(product_scope.Path("."), "product/prd.md", "prd")
        assert found is not None
        self.assertTrue(found.readable)
        self.assertEqual(found.data, data)
        self.assertEqual(found.warnings, ["warning: product/prd.md: a thing to look at"])


class TheLimitsDefault(unittest.TestCase):
    def test_the_default_is_ten_and_the_review_cycle_thirty(self):
        from aidd import config

        self.assertEqual(config.EMPTY.max_intent_specs, 10)
        self.assertEqual(product_checks.default_review_days(), 30)


class WhatAnApprovalCovers(unittest.TestCase):
    """`changes_since`: a change to anything an approved Intent holds, but the fields an agent keeps current, asks for the approval again."""

    BASE = intent(serves="Outcome-1")

    def test_each_field_the_approval_covers_has_its_row(self):
        check = [{"id": "S1", "metric": {"name": "Other", "source": "a report", "target": "2 days"}, "measure_after_days": 60}]
        for name, now, want in (
            ("as approved", {**self.BASE}, []),
            ("the outcome", {**self.BASE, "outcome": "Another outcome."}, ["its outcome changed"]),
            ("the item it serves", {**self.BASE, "serves": "Outcome-2"}, ["its serves changed"]),
            ("its success criteria", {**self.BASE, "success_criteria": check}, ["its success criteria changed"]),
            ("the title", {**self.BASE, "title": "Another title"}, ["its title changed"]),
            ("a field an agent keeps current", {**self.BASE, "owner": "maya", "blocked_by": ["INTENT-9"]}, []),
        ):
            with self.subTest(name):
                self.assertEqual(intents.changes_since(self.BASE, now), want)
        self.assertEqual(intents.changes_since(self.BASE, {**self.BASE, "owner": "maya"}), [], "the list of what an agent keeps is `AGENT_KEPT`")


if __name__ == "__main__":
    unittest.main()
