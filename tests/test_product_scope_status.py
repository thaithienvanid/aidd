"""What `aidd status` says of the product scope: an Intent is `approved` once an approval holds and no slice started, the Intents come in
the order of the intent order, a product outcome no Intent carries is stalled, the Intents in flight are counted against the
limit, and `aidd status product` shows the whole map. `aidd new` writes the files, and the order beside them.
A repository with no product scope hears none of it."""

import contextlib
import json
import unittest

import helpers  # noqa: F401  (puts src on sys.path)
from helpers import run_cli
from product_scope_fixtures import (
    CRITERION,
    MET,
    PERSON,
    RETIRED,
    ScopeCase,
    brd,
    intent,
    order,
    outcome,
    prd,
    requirement,
    standing,
    standing_outcomes,
    text,
)

from aidd import config, workitems
from aidd.cli import grammar
from aidd.kernel import json_schema
from aidd.workitems import product_map, product_scope, status, work_list


def scope_of(case: ScopeCase, files: dict) -> product_scope.ProductScope:
    for rel, data in files.items():
        case.write(rel, data)
    return product_scope.read(case.root, "product")


class TheDerivedApprovedStatus(ScopeCase):
    def status_of(self, iid: str = "INTENT-1") -> dict:
        found = [i for i in workitems.open_work(self.root, self.config(), include_done=True)["items"] if i["id"] == iid]
        return found[0]

    def test_an_intent_is_approved_while_an_approval_holds_and_no_slice_started(self):
        base = intent()
        merged = {**base, "phases": [{"id": "P1", "name": "p", "specs": [{"id": "SPEC-1-1", "title": "t", "merged_in": "1a2b3c4"}]}]}
        cases = [
            ("nobody approved", lambda: self.write("product/intents/INTENT-1.md", base), "draft", "backlog"),
            (
                "approved in the file, and no commit holds it",
                lambda: self.write("product/intents/INTENT-1.md", {**base, "approval": {"by": PERSON, "at": "2027-01-10T09:00:00Z"}}),
                "draft",
                "backlog",
            ),
            ("approved, and a commit holds it", lambda: self.approve_intent("product/intents/INTENT-1.md", base), "approved", "unstarted"),
            ("approved, and a slice merged", lambda: self.approve_intent("product/intents/INTENT-1.md", merged), "active", "started"),
            (
                "approved, and then the outcome changed",
                lambda: self.write("product/intents/INTENT-1.md", {**self.approve_intent("product/intents/INTENT-1.md", base), "outcome": "Another outcome."}),
                "approved",
                "unstarted",
            ),
            ("approved, and then closed", lambda: self.approve_intent("product/intents/INTENT-1.md", {**base, "status": "done"}), "done", "completed"),
        ]
        for name, write, state, group in cases:
            with self.subTest(name):
                self.fresh()
                write()
                shown = self.status_of()
                self.assertEqual((shown["status"], shown["group"]), (state, group))

    def test_a_change_after_the_approval_leaves_it_approved_and_asks_for_it_again(self):
        agreed = self.approve_intent("product/intents/INTENT-1.md", intent())
        self.write("product/intents/INTENT-1.md", {**agreed, "outcome": "Another outcome."})
        shown = self.status_of()
        self.assertEqual(shown["status"], "approved")
        self.assertEqual(shown["next"]["code"], "intent.approve")

    def test_a_change_to_what_the_approval_covers_asks_for_it_again_and_a_field_an_agent_keeps_does_not(self):
        check = [{"id": "S1", "metric": {"name": "Other", "source": "a report", "target": "2 days"}, "measure_after_days": 60}]
        for name, change, code in (
            ("the item it serves", {"serves": "Outcome-2"}, "intent.approve"),
            ("its success criteria", {"success_criteria": check}, "intent.approve"),
            ("the outcome", {"outcome": "Another outcome."}, "intent.approve"),
            ("the title", {"title": "Another title"}, "intent.approve"),
            ("a field an agent keeps current", {"owner": "maya"}, "intent.slice"),
        ):
            with self.subTest(name):
                self.fresh()
                self.write("product/outcomes.md", standing_outcomes([standing(1), standing(2)]))
                agreed = self.approve_intent("product/intents/INTENT-1.md", intent(serves="Outcome-1"))
                self.write("product/intents/INTENT-1.md", {**agreed, **change})
                shown = self.status_of()
                self.assertEqual((shown["status"], shown["next"]["code"]), ("approved", code))
                errors, warnings, _ = self.repository_check()
                self.assertEqual(
                    len(self.said(warnings, "product/intents/INTENT-1.md", "approve it again"))
                    if code == "intent.approve"
                    else len(self.said(warnings, "approve it again")),
                    1 if code == "intent.approve" else 0,
                    warnings,
                )

    def test_an_approved_by_line_alone_is_no_approval(self):
        self.write("product/intents/INTENT-1.md", intent())
        self.commit("plan")
        self.write("product/intents/INTENT-1.md", {**intent(), "approval": {"by": PERSON, "at": "2027-01-10T09:00:00Z"}})
        self.commit("approve", f"Approved-by: {PERSON}")
        self.assertEqual(self.status_of()["status"], "draft")

    def test_a_status_the_file_stores_is_never_taken_as_approved(self):
        self.write("product/intents/INTENT-1.md", {**intent(), "status": "approved"})
        errors, _ = workitems.check_repo(self.root)
        self.assertTrue(self.said(errors, "derived from `approval` and the commit that holds it"), errors)


class EveryViewAgreesOnTheStatus(ScopeCase):
    """`aidd status`, `aidd status <ID>`, and `aidd validate` read the same Intent as approved."""

    def setUp(self):
        super().setUp()
        self.write("product/outcomes.md", standing_outcomes())
        self.approve_intent("product/intents/INTENT-1.md", intent(serves="Outcome-1"))
        self.write("specs/SPEC-1.md", "---\ntype: spec\nid: SPEC-1\ntitle: A Spec\nparent: INTENT-1\n---\n")

    def test_the_open_work_names_it_approved(self):
        items = {i["id"]: i for i in workitems.open_work(self.root, self.config())["items"]}
        self.assertEqual(items["INTENT-1"]["status"], "approved")

    def test_the_trace_of_a_child_shows_its_parent_approved(self):
        answer = workitems.trace(self.root, self.config(), "SPEC-1", commits=1)
        self.assertEqual({w["id"]: w["status"] for w in answer["work"]}["INTENT-1"], "approved")

    def test_validate_reads_it_approved(self):
        _, warnings, _ = self.repository_check()
        self.write("product/intents/order.md", order([]))
        _, warnings, _ = self.repository_check()
        self.assertEqual(len(self.said(warnings, "order.md", "INTENT-1")), 1, "an Intent validate reads as approved is the one the order leaves out")


class TheDerivedStatusAgainstTheOne(unittest.TestCase):
    """An Intent's status, new against old over every combination of what it reads: with no approval it gives what it gave, and
    an approval changes one answer, a draft, into approved."""

    STORED = (None, "draft", "active", "done", "cancelled", "approved", "bogus")
    DECISIONS = (None, "go", "no_go")
    CHILDREN = ([], ["draft"], ["in_progress"], ["done"], ["draft", "in_progress"], ["cancelled"], ["ready", "approved"])

    @staticmethod
    def before(data: dict, children: list[str]) -> str:
        s = status.stored_status(data)
        if s in status.INTENT_ENDED:
            return str(s)
        if (data.get("go_no_go") or {}).get("decision") == "no_go":
            return "cancelled"
        if not children:
            return s if s is not None and s in status.INTENT_STATUSES and s not in status.INTENT_NEVER_STORED else config.initial_status("intent")
        return "active" if any(c in status.STARTED for c in children) else "draft"

    def test_no_approval_gives_the_old_answer_and_an_approval_turns_only_a_draft_into_approved(self):
        seen = set()
        for stored in self.STORED:
            for decision in self.DECISIONS:
                for children in self.CHILDREN:
                    data = {**({"status": stored} if stored else {}), **({"go_no_go": {"decision": decision}} if decision else {})}
                    with self.subTest(stored=stored, decision=decision, children=children):
                        old = self.before(data, children)
                        self.assertEqual(status.intent_status(data, children), old)
                        self.assertEqual(status.intent_status(data, children, True), "approved" if old == "draft" else old)
                        seen.add(old)
        self.assertEqual(seen, {"draft", "active", "done", "cancelled"}, "the set reaches every answer the old one gave")


class TheStalledItems(ScopeCase):
    """Rows: the files, the Intents as (status, whether it holds a result), and the items no Intent carries."""

    BRD_AND_PRD = {"product/brd.md": brd(), "product/prd.md": prd()}

    def stalled(self, files: dict, rows: dict[str, tuple[str, str, bool]]) -> list[str]:
        self.fresh()
        scope = scope_of(self, files)
        read = {"measured_on": "2027-01-05", "actual": "1", "source": "report", "decision": "met"}
        intents = {
            iid: (state, {"serves": serves, "success_criteria": [{**CRITERION, **({"result": read} if result else {})}]})
            for iid, (state, serves, result) in rows.items()
        }
        return [i.id for i in product_map.stalled(scope, intents)]

    def test_an_active_item_with_no_intent_that_carries_it_is_stalled(self):
        cases = [
            ("no Intent", self.BRD_AND_PRD, {}, ["Outcome-1"]),
            ("a draft Intent", self.BRD_AND_PRD, {"INTENT-1": ("draft", "Outcome-1", False)}, ["Outcome-1"]),
            ("an approved Intent", self.BRD_AND_PRD, {"INTENT-1": ("approved", "Outcome-1", False)}, []),
            ("an active Intent", self.BRD_AND_PRD, {"INTENT-1": ("active", "Outcome-1", False)}, []),
            ("a done Intent whose result is to come", self.BRD_AND_PRD, {"INTENT-1": ("done", "Outcome-1", False)}, []),
            ("a done Intent that has its result", self.BRD_AND_PRD, {"INTENT-1": ("done", "Outcome-1", True)}, ["Outcome-1"]),
            ("a cancelled Intent", self.BRD_AND_PRD, {"INTENT-1": ("cancelled", "Outcome-1", False)}, ["Outcome-1"]),
            (
                "an Intent that serves another item",
                {"product/prd.md": prd([outcome(1, None), outcome(2, None)])},
                {"INTENT-1": ("active", "Outcome-2", False)},
                ["Outcome-1"],
            ),
            (
                "two Intents, one of them carrying it",
                self.BRD_AND_PRD,
                {"INTENT-1": ("cancelled", "Outcome-1", False), "INTENT-2": ("approved", "Outcome-1", False)},
                [],
            ),
            ("a met outcome", {"product/prd.md": prd([outcome(1, None, results=[MET])])}, {}, []),
            ("a retired outcome", {"product/prd.md": prd([outcome(1, None, results=[RETIRED])])}, {}, []),
            ("a requirement, with a PRD", self.BRD_AND_PRD, {"INTENT-1": ("approved", "Outcome-1", False)}, []),
            ("a requirement, with no PRD", {"product/brd.md": brd()}, {}, ["Requirement-1"]),
            ("a requirement, with no PRD, carried", {"product/brd.md": brd()}, {"INTENT-1": ("approved", "Requirement-1", False)}, []),
            ("a standing outcome", {"product/outcomes.md": standing_outcomes()}, {}, ["Outcome-1"]),
            ("a standing outcome, carried", {"product/outcomes.md": standing_outcomes()}, {"INTENT-1": ("active", "Outcome-1", False)}, []),
            ("no product scope", {}, {}, []),
            ("a product scope that did not read", {"product/prd.md": "---\ntype: prd\noutcomes: not a list\n---\n"}, {}, []),
        ]
        for name, files, rows, want in cases:
            with self.subTest(name):
                self.assertEqual(self.stalled(files, rows), want)

    def test_a_done_intent_carries_its_item_until_every_criterion_has_a_result(self):
        self.fresh()
        scope = scope_of(self, self.BRD_AND_PRD)
        read = {"measured_on": "2027-01-05", "actual": "1", "source": "report", "decision": "met"}
        second = {**CRITERION, "id": "S2"}
        for name, criteria, want in (
            ("none has one", [CRITERION, second], []),
            ("one has one", [{**CRITERION, "result": read}, second], []),
            ("each has one", [{**CRITERION, "result": read}, {**second, "result": read}], ["Outcome-1"]),
            ("no criteria at all", [], []),
        ):
            with self.subTest(name):
                intents = {"INTENT-1": ("done", {"serves": "Outcome-1", "success_criteria": criteria})}
                self.assertEqual([i.id for i in product_map.stalled(scope, intents)], want)

    def test_a_requirement_that_no_outcome_serves_is_for_a_person(self):
        self.fresh()
        files = {"product/brd.md": brd(requirements=[requirement(1), requirement(2)]), "product/prd.md": prd([outcome(1, "Requirement-1")])}
        scope = scope_of(self, files)
        self.assertEqual([i.id for i in product_map.uncovered(scope)], ["Requirement-2"])
        self.assertEqual(product_map.stalled(scope, {}), [scope.items["Outcome-1"]], "the outcome is stalled; the requirement is not an agent's step")

    def test_a_requirement_the_prd_holds_beside_a_brd_is_to_move_and_asks_for_no_outcome(self):
        self.fresh()
        files = {
            "product/brd.md": brd(requirements=[requirement(1)]),
            "product/prd.md": prd([outcome(1, "Requirement-1")], requirements=[requirement(2, None)]),
        }
        self.assertEqual(product_map.uncovered(scope_of(self, files)), [])

    def test_the_intents_in_flight_are_the_approved_and_the_active(self):
        rows = {f"INTENT-{n}": (state, {}) for n, state in enumerate(("draft", "approved", "active", "done", "cancelled"), 1)}
        self.assertEqual(product_map.in_flight(rows), 2)
        self.assertEqual(product_map.in_flight({}), 0)


class TheLinesOfTheOpenWork(ScopeCase):
    def answer(self, **kwargs) -> dict:
        return workitems.open_work(self.root, self.config(), **kwargs)

    def test_a_product_scope_adds_its_stalled_items_and_the_intents_in_flight(self):
        self.write("product/prd.md", prd([outcome(1, None), outcome(2, None)]))
        self.write("product/intents/order.md", order([], max_in_flight=2))
        self.approve_intent("product/intents/INTENT-1.md", intent(serves="Outcome-1"))
        summary = self.answer()["product_scope"]
        self.assertEqual([s["id"] for s in summary["stalled"]], ["Outcome-2"])
        self.assertEqual(summary["stalled"][0]["next"]["code"], "product_scope.stalled")
        self.assertEqual((summary["in_flight_count"], summary["max_in_flight"]), (1, 2))

    def test_the_limit_is_left_out_when_the_order_sets_none(self):
        self.write("product/prd.md", prd([outcome(1, None)]))
        self.assertNotIn("max_in_flight", self.answer()["product_scope"])

    def test_with_no_product_scope_the_answer_has_none(self):
        self.write("product/intents/INTENT-1.md", intent())
        self.assertNotIn("product_scope", self.answer())

    def test_the_answer_follows_the_status_schema(self):
        self.write("product/prd.md", prd([outcome(1, None)]))
        self.write("product/intents/order.md", order([], max_in_flight=3))
        self.approve_intent("product/intents/INTENT-1.md", intent(serves="Outcome-1"))
        shown = {"schema_version": "1", **self.answer()}
        self.assertEqual(json_schema.validate(shown, "status.schema.json"), [])

    def test_the_text_says_each_line_to_the_one_who_takes_it(self):
        self.write("product/prd.md", prd([outcome(1, None), outcome(2, None)]))
        self.write("product/intents/order.md", order([], max_in_flight=2))
        self.approve_intent("product/intents/INTENT-1.md", intent(serves="Outcome-1"))
        answer = self.answer()
        for who, stalled, in_flight in ((None, True, True), ("agent", True, False), ("person", False, False)):
            with self.subTest(who=who):
                said = work_list.status_text(answer, who=who)
                self.assertEqual("stalled: Outcome-2" in said, stalled, said)
                self.assertEqual("in flight: 1 of at most 2 Intents" in said, in_flight, said)

    def test_the_intents_in_flight_say_one_and_say_when_the_limit_is_passed(self):
        for count, limit, want in (
            (1, None, "1 Intent (approved or active)"),
            (3, None, "3 Intents (approved or active)"),
            (1, 1, "1 of at most 1 Intent (approved or active)"),
            (1, 4, "1 of at most 4 Intents (approved or active)"),
            (4, 4, "4 of at most 4 Intents (approved or active)"),
            (5, 4, "5 of at most 4 Intents (approved or active): over the limit"),
        ):
            with self.subTest(count=count, limit=limit):
                said = work_list.in_flight_words(count, limit)
                self.assertTrue(said.startswith(want), said)
                self.assertEqual("over the limit" in said, limit is not None and count > limit)

    def test_the_step_prints_what_it_is_and_never_the_words_a_person_hears(self):
        self.write("product/prd.md", prd([outcome(1, None)]))
        answer = self.answer()
        step = answer["product_scope"]["stalled"][0]["next"]
        said = work_list.status_text(answer)
        self.assertIn(f"next (agent): {step['what']}", said)
        self.assertNotIn(step["words"], said)
        self.assertNotIn(step["words"], workitems.product_status_text(workitems.product_status(self.root, self.config())))

    def test_stalled_items_are_never_printed_beside_nothing_is_open(self):
        self.write("product/prd.md", prd([outcome(1, None)]))
        answer = self.answer()
        self.assertEqual(answer["items"], [])
        self.assertNotIn("next", answer)
        self.assertNotIn("nothing", work_list.status_text(answer).lower())
        self.fresh()
        self.assertEqual(self.answer()["next"]["code"], "nothing_open", "with nothing stalled, it still says so")

    def test_the_line_for_the_intents_in_flight_is_left_out_when_there_is_nothing_to_say(self):
        self.write("product/prd.md", prd([outcome(1, None)]))
        self.assertNotIn("in flight", work_list.status_text(self.answer()))

    def test_the_intents_come_in_the_order_of_the_intent_order_and_an_unlisted_one_last(self):
        for n in (1, 2, 3):
            self.write(f"product/intents/INTENT-{n}.md", intent(f"INTENT-{n}"))
        for ids, want in (
            ([], ["INTENT-1", "INTENT-2", "INTENT-3"]),
            (["INTENT-3", "INTENT-1"], ["INTENT-3", "INTENT-1", "INTENT-2"]),
            (["INTENT-2", "INTENT-3", "INTENT-1"], ["INTENT-2", "INTENT-3", "INTENT-1"]),
        ):
            with self.subTest(order=ids):
                self.write("product/intents/order.md", order(ids))
                self.assertEqual([i["id"] for i in self.answer()["items"]], want)

    def test_an_order_that_does_not_read_ranks_nothing(self):
        for n in (1, 2):
            self.write(f"product/intents/INTENT-{n}.md", intent(f"INTENT-{n}"))
        self.write("product/intents/order.md", "---\ntype: intent-order\norder: not a list\n---\n")
        self.assertEqual([i["id"] for i in self.answer()["items"]], ["INTENT-1", "INTENT-2"])


class TheProductView(ScopeCase):
    def setUp(self):
        super().setUp()
        self.write("product/brd.md", brd())
        self.write("product/prd.md", prd([outcome(1, "Requirement-1"), outcome(2, "Requirement-1")]))
        self.write("product/intents/order.md", order(["INTENT-2", "INTENT-1"], max_in_flight=3))
        self.approve_intent("product/intents/INTENT-1.md", intent("INTENT-1", serves="Outcome-1"))
        self.write("product/intents/INTENT-2.md", intent("INTENT-2", serves="Outcome-1"))
        self.write(
            "product/intents/INTENT-3.md",
            {
                **intent(
                    "INTENT-3",
                    serves="Outcome-1",
                    success_criteria=[{**CRITERION, "result": {"measured_on": "2027-01-05", "actual": "50%", "source": "report", "decision": "continue"}}],
                ),
                "status": "done",
            },
        )
        self.write(
            "specs/SPEC-3-1.md",
            {"type": "spec", "id": "SPEC-3-1", "title": "A slice", "status": "done", "parent": "INTENT-3", "outcome": {"released_on": "2027-01-02"}},
        )

    def shown(self) -> dict:
        return workitems.product_status(self.root, self.config())

    def test_it_follows_its_schema_and_shows_the_shape(self):
        shown = self.shown()
        self.assertEqual(json_schema.validate({"schema_version": "1", **shown}, "product-status.schema.json"), [])
        self.assertEqual(shown["shape"], ["brd", "prd"])

    def test_the_open_intents_come_first_in_order_then_the_closed_with_their_result(self):
        rows = self.shown()["intents"]
        self.assertEqual([r["id"] for r in rows], ["INTENT-2", "INTENT-1", "INTENT-3"])
        self.assertEqual(
            rows[2]["criteria"],
            [
                {
                    "id": "S1",
                    "address": "INTENT-3#S1",
                    "metric_name": "Wait",
                    "measure_from": "2027-02-01",
                    "result": {"measured_on": "2027-01-05", "decision": "continue"},
                }
            ],
        )
        self.assertEqual([r["status"] for r in rows], ["draft", "approved", "done"])

    def test_each_item_names_the_intents_that_serve_it(self):
        items = {i["id"]: i for i in self.shown()["items"]}
        self.assertEqual(items["Outcome-1"]["intents"], ["INTENT-2", "INTENT-1", "INTENT-3"], "in the order the Intents are shown")
        self.assertEqual(items["Outcome-2"]["intents"], [])
        self.assertEqual(items["Requirement-1"]["serves"], "Objective-1")

    def test_a_file_says_whether_a_person_approved_it_and_what_changed(self):
        approved = self.approve("product/prd.md", prd([outcome(1, "Requirement-1")]))
        states = lambda: {f["path"]: f["state"] for f in self.shown()["files"]}  # noqa: E731
        self.assertEqual(states()["product/prd.md"], "approved")
        self.assertEqual(states()["product/brd.md"], "not_approved")
        self.write("product/prd.md", {**approved, "outcomes": [outcome(1, "Requirement-1"), outcome(2, "Requirement-1")]})
        row = [f for f in self.shown()["files"] if f["type"] == "prd"][0]
        self.assertEqual((row["state"], row["changed"]), ("changed", "Outcome-2 added"))
        self.assertEqual(row["next"]["code"], "product_scope.approve")
        self.assertEqual(row["next"]["who"], "person")

    def test_the_stalled_and_the_flight_are_in_the_view(self):
        shown = self.shown()
        self.assertEqual([s["id"] for s in shown["stalled"]], ["Outcome-2"])
        self.assertEqual((shown["in_flight_count"], shown["max_in_flight"]), (1, 3))

    def test_the_text_reads_as_a_page_of_plain_lines(self):
        said = workitems.product_status_text(self.shown())
        for want in (
            "The product scope is a BRD and a PRD.",
            "product/prd.md: not approved",
            "In flight: 1 of at most 3 Intents (approved or active).",
            "Stalled: Outcome-2",
            "Outcome-1 Customers get a quick answer (outcome, active): serves Requirement-1; INTENT-2, INTENT-1, INTENT-3",
            "INTENT-3 Quicker answers (done)",
        ):
            self.assertIn(want, said)
        self.assertLess(said.index("INTENT-2 Quicker"), said.index("INTENT-1 Quicker"))

    def test_it_carries_findings_as_the_open_work_does(self):
        self.assertEqual(self.shown()["findings"], [])
        self.write("product/prd.md", "---\ntype: prd\noutcomes: not a list\n---\n")
        shown = {"schema_version": "1", **self.shown()}
        self.assertEqual(json_schema.validate(shown, "product-status.schema.json"), [])
        self.assertEqual([(f["code"], f["path"]) for f in shown["findings"]], [("status.unreadable_item", "product/prd.md")])
        with contextlib.chdir(self.root):
            code, out = run_cli("status", "product", "--json")
        self.assertEqual((code, json.loads(out)["findings"][0]["path"]), (0, "product/prd.md"))

    def test_a_file_that_does_not_read_says_where_to_look(self):
        self.write("product/prd.md", "---\ntype: prd\noutcomes: not a list\n---\n")
        shown = self.shown()
        self.assertEqual([f["state"] for f in shown["files"] if f["type"] == "prd"], ["unreadable"])
        self.assertIn("product/prd.md: unreadable: `aidd validate` says why", workitems.product_status_text(shown))

    def test_with_no_product_scope_it_says_how_to_write_one(self):
        self.fresh()
        shown = self.shown()
        self.assertEqual(shown["files"], [])
        self.assertEqual(json_schema.validate({"schema_version": "1", **shown}, "product-status.schema.json"), [])
        self.assertIn("`aidd new prd`", workitems.product_status_text(shown))

    def test_the_command_reads_it_from_the_repository_and_from_a_subfolder(self):
        (self.root / "specs" / "deep").mkdir(parents=True)
        for where in (".", "specs/deep"):
            with self.subTest(where=where), contextlib.chdir(self.root / where):
                code, out = run_cli("status", "product")
                self.assertEqual(code, 0, out)
                self.assertIn("The product scope is a BRD and a PRD.", out)
                code, out = run_cli("status", "product", "--json")
                self.assertEqual(code, 0, out)
                self.assertEqual(json.loads(out)["shape"], ["brd", "prd"])

    def test_a_flag_it_does_not_read_is_refused_with_the_way_on(self):
        with contextlib.chdir(self.root):
            for flag, want in (("--html", "--json"), ("--who", "only --json"), ("--all-branches", "only --json")):  # each flag it does not read
                with self.subTest(flag):
                    code, out = run_cli("status", "product", flag, *(["agent"] if flag == "--who" else []))
                    self.assertEqual(code, 2, out)
                    self.assertIn(want, out)

    def test_a_typo_of_the_word_gets_a_hint_and_a_real_path_none(self):
        with contextlib.chdir(self.root):
            for word, hinted in (("produkt", True), ("prodct", True), ("specs", False), ("somewhere", False)):
                with self.subTest(word):
                    code, out = run_cli("status", word)
                    self.assertEqual(code, 0, out)
                    self.assertEqual("Did you mean `product`?" in out, hinted, out)

    def test_the_folder_of_that_name_is_still_read_as_a_path_with_a_slash(self):
        with contextlib.chdir(self.root):
            code, out = run_cli("status", "product/", "--json")
            self.assertEqual(code, 0, out)
            self.assertIn("work", json.loads(out))


class TheNewCommands(ScopeCase):
    def new(self, *argv: str, where: str = ".") -> tuple[int, str]:
        self.start()
        with contextlib.chdir(self.root / where):
            return run_cli("new", *argv)

    def test_each_type_writes_its_file_and_the_order_beside_it(self):
        for item_type, name in (("brd", "brd.md"), ("prd", "prd.md"), ("standing-outcomes", "outcomes.md")):
            with self.subTest(item_type):
                self.fresh()
                code, out = self.new(item_type)
                self.assertEqual(code, 0, out)
                self.assertTrue((self.root / "product" / name).is_file())
                self.assertTrue((self.root / "product" / "intents" / "order.md").is_file())
                self.assertEqual(out.splitlines()[:2], [f"product/{name}", "product/intents/order.md"])
                self.assertIn("next: ", out)
                self.assertIn("aidd validate", out)

    def test_an_order_that_exists_is_left_as_it_is(self):
        self.write("product/intents/order.md", order(["INTENT-1"]))
        code, out = self.new("prd")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.strip().splitlines()[0], "product/prd.md")
        self.assertIn("INTENT-1", (self.root / "product/intents/order.md").read_text(encoding="utf-8"))

    def test_the_intent_order_alone_is_a_type_of_its_own(self):
        code, out = self.new("intent-order")
        self.assertEqual((code, out.splitlines()[0]), (0, "product/intents/order.md"))
        self.assertFalse((self.root / "product" / "prd.md").exists())

    def test_a_file_that_exists_is_never_written_over(self):
        self.write("product/prd.md", prd())
        code, out = self.new("prd")
        self.assertEqual(code, 2, out)
        self.assertIn("exists", out)
        self.assertEqual((self.root / "product/prd.md").read_text(encoding="utf-8"), text(prd()))

    def test_standing_outcomes_and_a_brd_or_a_prd_are_never_written_together(self):
        for have, want_new in (
            ("product/prd.md", "standing-outcomes"),
            ("product/brd.md", "standing-outcomes"),
            ("product/outcomes.md", "prd"),
            ("product/outcomes.md", "brd"),
        ):
            with self.subTest(have=have, new=want_new):
                self.fresh()
                self.write(have, "---\ntype: prd\n---\n")
                code, out = self.new(want_new)
                self.assertEqual(code, 2, out)
                self.assertIn("neither a BRD nor a PRD", out)
                self.assertIn(have, out)

    def test_a_typo_and_an_id_are_refused(self):
        with self.assertRaises(SystemExit) as typo:
            self.new("brdd")
        self.assertEqual(typo.exception.code, 2)
        code, out = self.new("brd", "BRD-1")
        self.assertEqual(code, 2, out)
        self.assertIn("aidd new brd", out)
        self.assertFalse((self.root / "product").exists())

    def test_it_writes_in_the_repository_from_a_subfolder(self):
        (self.root / "specs").mkdir()
        code, out = self.new("prd", where="specs")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.root / "product" / "prd.md").is_file())

    def test_the_product_folder_is_the_configs(self):
        self.write(".aidd/config.yaml", 'aidd_version: "1.0.0"\nprofile: solo\nproduct_dir: plan\n')
        code, out = self.new("prd")
        self.assertEqual((code, out.splitlines()[:2]), (0, ["plan/prd.md", "plan/intents/order.md"]))

    def test_the_lists_offer_each_type(self):
        offered = [name for _, types in grammar.new_type_groups() for name in types]
        for name in ("brd", "prd", "standing-outcomes", "intent-order"):
            self.assertIn(name, offered)


if __name__ == "__main__":
    unittest.main()
