"""The status tables: which status follows which, who moves it, and the facts about each status, are data in the schemas, and every
reader reads them. A status table is the node its row of schemas/item-types.json points to: the words (`enum`), their meanings and
groups, the status a new item starts in (`x-initial`), the sets of statuses that code reads (`x-sets`), and each move
(`x-transitions`).

The Spec's approval and revision rules are controls, so they are pinned here as a table of every pair of statuses: a move that is
not listed does not exist, an agent alone never lowers an approved Spec, and only a person's yes sets one back to `draft`, with a
`revisions` entry (`spec.revise`). No module of `src/aidd` keeps a list of statuses of its own."""

from __future__ import annotations

import ast
import functools
import itertools
import unittest

import helpers  # noqa: F401  # puts src/ on the path and makes the run hermetic
from helpers import ROOT, validate_with
from test_proposal import ACCEPTED, BASE, GO, SIGNED, SUBMITTED, load
from test_workitems import Base, intent, spec

from aidd import config, workitems
from aidd.kernel import resources
from aidd.knowledge import explanations
from aidd.workitems import status, validation

SRC = ROOT / "src" / "aidd"
COMMON = resources.load_json("common.schema.json")["$defs"]
TYPES = config.types_of_form("work_item")

# Every move that exists, by type: (the statuses it leaves, the status it reaches, who moves it). A pair that no row here reaches
# is refused, and the table below is checked pair by pair.
MOVES = {
    "spec": {
        ("draft", "ready", "agent"),
        ("ready", "approved", "person"),
        ("ready", "approved", "agent"),
        ("approved", "in_progress", "agent"),
        ("in_progress", "in_review", "agent"),
        ("in_review", "in_progress", "agent"),
        ("approved", "draft", "person"),
        ("in_progress", "draft", "person"),
        ("in_review", "draft", "person"),
        ("in_review", "done", "person"),
        ("done", "rolled_back", "person"),
        ("draft", "cancelled", "person"),
        ("ready", "cancelled", "person"),
        ("approved", "cancelled", "person"),
        ("in_progress", "cancelled", "person"),
        ("in_review", "cancelled", "person"),
    },
    "intent": {
        ("draft", "approved", "person"),
        ("draft", "active", "agent"),
        ("approved", "active", "agent"),
        ("draft", "done", "person"),
        ("approved", "done", "person"),
        ("active", "done", "person"),
        ("done", "active", "person"),
        ("draft", "cancelled", "person"),
        ("approved", "cancelled", "person"),
        ("active", "cancelled", "person"),
    },
    "proposal": {
        ("qualifying", "no_go", "person"),
        ("qualifying", "drafting", "person"),
        ("drafting", "signed_off", "person"),
        ("signed_off", "submitted", "person"),
        ("submitted", "accepted", "person"),
        ("submitted", "rejected", "person"),
        ("qualifying", "withdrawn", "person"),
        ("drafting", "withdrawn", "person"),
        ("signed_off", "withdrawn", "person"),
        ("submitted", "withdrawn", "person"),
    },
}
# What a Spec's sets hold today, written out so a change to the data is a change to this table too.
SPEC_SETS = {
    "past_approval": {"approved", "in_progress", "in_review", "done", "rolled_back"},
    "before_implement": {"draft", "ready", "approved"},
    "specifying": {"draft", "ready"},
    "implementing": {"approved", "in_progress"},
    "can_wait": {"draft", "ready", "approved", "in_progress"},
    "built": {"in_review", "done", "rolled_back"},
    "started": {"in_progress", "in_review", "done", "rolled_back"},
    "ended": {"done", "rolled_back", "cancelled"},
    "landed": {"done"},
    "asked": {"ready", "approved", "in_progress", "in_review", "done"},
    "in_the_srs": {"approved", "in_progress", "in_review", "done"},
    "acceptance_due": {"in_review", "done"},
    "without_triage": {"draft", "cancelled"},
}
# The constant of `aidd.workitems.status` that holds each Spec set.
SPEC_CONSTANTS = {
    "past_approval": "PAST_APPROVAL",
    "before_implement": "BEFORE_IMPLEMENT",
    "specifying": "SPECIFYING",
    "implementing": "IMPLEMENTING",
    "can_wait": "CAN_WAIT",
    "built": "BUILT",
    "ended": "TERMINAL",
    "landed": "LANDED_STATUSES",
    "asked": "ASKED",
    "in_the_srs": "IN_THE_SRS",
    "acceptance_due": "ACCEPTANCE_DUE",
    "without_triage": "WITHOUT_TRIAGE",
}
# A list of two or more statuses that lives in the code, with why it is no copy of a status table.
OWN_LISTS: dict[str, str] = {}


def table(item_type: str) -> dict:
    return config.status_table(item_type)


def moves(item_type: str) -> set[tuple[str, str, str]]:
    return {(s, m["to"], m["who"]) for m in config.status_transitions(item_type) for s in m["from"]}


class TheTables(unittest.TestCase):
    def test_a_table_holds_the_facts_its_schema_says(self):
        for name in TYPES:
            enum = table(name)["enum"]
            with self.subTest(type=name):
                for key in ("x-initial", "x-sets", "x-transitions"):
                    self.assertIn(key, table(name))
                self.assertIn(table(name)["x-initial"]["status"], enum)
                self.assertEqual(validate_with(table(name)["x-initial"], COMMON["status_start"]), [])
                for set_name, row in table(name)["x-sets"].items():
                    self.assertEqual(validate_with(row, COMMON["status_set"]), [], set_name)
                    self.assertEqual(row["statuses"], [s for s in enum if s in row["statuses"]], f"{set_name}: the statuses stand in the order of the enum")
                for move in config.status_transitions(name):
                    self.assertEqual(validate_with(move, COMMON["status_transition"]), [], str(move))
                    self.assertLessEqual({*move["from"], move["to"]}, set(enum), str(move))
                    self.assertNotIn(move["to"], move["from"], f"a status never moves to itself: {move}")
                    schema = resources.load_json(config.item_type_rows()[name]["schema"])
                    self.assertLessEqual(set(move.get("requires", [])), set(schema["properties"]), f"a move sets fields of the {name} schema: {move}")

    def test_a_move_is_listed_once(self):
        for name in TYPES:
            listed = [(s, m["to"], m["who"]) for m in config.status_transitions(name) for s in m["from"]]
            with self.subTest(type=name):
                self.assertEqual(len(listed), len(set(listed)))

    def test_every_pair_of_statuses_is_a_move_or_is_refused(self):
        """The generated table: each ordered pair of each type's statuses, against the moves written out above."""
        for name in TYPES:
            legal = {(a, b) for a, b, _ in MOVES[name]}
            self.assertEqual(moves(name), MOVES[name], f"the {name} moves are the table above")
            for a, b in itertools.product(table(name)["enum"], repeat=2):
                with self.subTest(type=name, move=f"{a} -> {b}"):
                    found = {(m["to"], m["who"]) for m in config.status_transitions(name) if a in m["from"] and m["to"] == b}
                    self.assertEqual(bool(found), (a, b) in legal)

    def test_the_sets_a_spec_is_read_by(self):
        for set_name, want in SPEC_SETS.items():
            with self.subTest(set=set_name):
                self.assertEqual(config.status_set("spec", set_name), want)
        self.assertEqual(set(table("spec")["x-sets"]), set(SPEC_SETS))

    def test_each_set_has_a_reader(self):
        """A set no code reads is dead data: its name is quoted in the code that asks for it."""
        code = {p: p.read_text(encoding="utf-8") for p in SRC.rglob("*.py") if "docsgen" not in p.parts}
        for name in TYPES:
            for set_name in table(name)["x-sets"]:
                with self.subTest(type=name, set=set_name):
                    self.assertTrue(any(f'"{set_name}"' in text for text in code.values()), f"nothing reads the set {set_name}")


class TheApprovalAndRevisionRules(unittest.TestCase):
    """`spec.revise` and Spec approval stay true in the data: only a person's yes lowers an approved Spec, and approval is reached from
    the status that asks for it."""

    def test_an_approved_spec_leaves_only_by_a_person_or_forward(self):
        for m in config.status_transitions("spec"):
            leaves = set(m["from"]) & status.IN_FLIGHT
            if leaves and m["to"] not in status.PAST_APPROVAL:
                with self.subTest(move=str(m)):
                    self.assertEqual(m["who"], "person", "an agent alone never lowers or stops an approved Spec")
                    if m["to"] == "draft":
                        self.assertEqual(m.get("requires"), ["revisions"], "a Spec set back to draft records the revision")

    def test_a_spec_reaches_approval_only_from_the_status_that_asks_for_it(self):
        reaching = [
            (m["from"], m["who"]) for m in config.status_transitions("spec") if m["to"] in status.PAST_APPROVAL and not set(m["from"]) & status.PAST_APPROVAL
        ]
        self.assertEqual(sorted(reaching), [(["ready"], "agent"), (["ready"], "person")])
        self.assertEqual(status.ASKS_APPROVAL, {"ready"})
        self.assertEqual(workitems.ASKS_APPROVAL, {"ready"})

    def test_a_status_past_approval_is_reached_only_by_a_move_that_sets_who_approved_it(self):
        """The person's move sets `approved_by` and `approved_at`; the agent's, where no yes is asked, sets `approved_at` alone."""
        by_person = {s for m in config.status_transitions("spec") if m["who"] == "person" and "approved_by" in m.get("requires", []) for s in [m["to"]]}
        self.assertEqual(by_person, {"approved"})

    def test_the_names_other_packages_read(self):
        self.assertEqual(workitems.SPEC_STATUSES, tuple(table("spec")["enum"]))
        self.assertEqual(workitems.PAST_APPROVAL, SPEC_SETS["past_approval"])
        self.assertEqual(workitems.BEFORE_IMPLEMENT, SPEC_SETS["before_implement"])
        self.assertEqual(workitems.FROZEN_STATUSES, {"approved", "in_progress", "in_review"})
        self.assertEqual(workitems.CAN_WAIT, SPEC_SETS["can_wait"])
        self.assertEqual(workitems.IMPLEMENTING, SPEC_SETS["implementing"])

    def test_the_test_run_s_sets_are_the_ones_its_literals_held(self):
        """The three sets `aidd test` decides by (testing.governing) hold what its own literals held before it read the tables."""
        from aidd.testing import governing

        held = {
            "IN_FLIGHT": {"approved", "in_progress", "in_review"},
            "NOT_BUILT": {"draft", "ready", "approved", "in_progress"},
            "OPEN": {"approved", "in_progress"},
        }
        self.assertEqual({name: set(getattr(governing, name)) for name in held}, held)
        self.assertEqual((workitems.FROZEN_STATUSES, workitems.CAN_WAIT, workitems.IMPLEMENTING), tuple(held.values()))


class TheCodeAgrees(unittest.TestCase):
    def test_a_status_the_code_does_not_know_is_in_no_set(self):
        for value in ("bogus", None, ["draft"], {"a": "b"}, 5, True, ""):
            with self.subTest(value=repr(value)):
                for name in SPEC_SETS:
                    self.assertNotIn(value, config.status_set("spec", name), name)

    def test_each_constant_is_its_set(self):
        for set_name, constant in SPEC_CONSTANTS.items():
            with self.subTest(set=set_name):
                self.assertEqual(getattr(status, constant), SPEC_SETS[set_name])
        self.assertEqual(status.STARTED, SPEC_SETS["started"] | {"active"}, "a child that started, of any type")
        self.assertEqual(status.IN_FLIGHT, {"approved", "in_progress", "in_review"})
        self.assertEqual(status.ENDED_UNLANDED, {"rolled_back", "cancelled"})
        self.assertEqual(status.INTENT_ENDED, {"done", "cancelled"})

    def test_a_new_item_starts_in_the_status_its_table_says(self):
        self.assertEqual({t: config.initial_status(t) for t in TYPES}, {"spec": "draft", "intent": "draft", "proposal": "qualifying"})
        self.assertEqual(status.spec_status({}), "draft")
        self.assertEqual(status.intent_status({}, []), "draft")

    def test_a_proposals_decisions_are_read_from_its_sets(self):
        from aidd.workitems import spec_file

        self.assertEqual(spec_file.PROPOSAL_NEEDS_GO, {"drafting", "signed_off", "submitted", "accepted", "rejected"})
        self.assertEqual(spec_file.PROPOSAL_NEEDS_SIGN_OFF, {"signed_off", "submitted", "accepted", "rejected"})
        self.assertEqual(spec_file.PROPOSAL_OUTCOMES, {"submitted", "accepted", "rejected", "withdrawn"})

    def test_explain_gives_each_status_its_moves(self):
        for name in TYPES:
            for word in table(name)["enum"]:
                out = [m for m in config.status_transitions(name) if word in m["from"]]
                answers = [
                    a
                    for a in explanations.explain(word)
                    if a["type"] == "status" and a["what"].startswith(f"The status of {config.item_type_rows()[name]['noun']}")
                ]
                with self.subTest(type=name, status=word):
                    self.assertEqual(len(answers), 1)
                    for m in out:
                        self.assertIn(f"`{m['to']}`", answers[0]["why"])
                    if not out:
                        self.assertIn("No move leaves it", answers[0]["why"])


class TheAdviceByStatus(Base):
    """What `aidd status` and `aidd validate` say of an item in each status stays what it was before the tables were data: the group
    and the next step of a Spec in each status, the Intent a person closed and the one its slices make active, and the decisions a
    proposal's status needs on record."""

    SPEC = {
        "draft": ("backlog", "spec.draft"),
        "ready": ("unstarted", "spec.approve"),
        "approved": ("unstarted", "spec.approved"),
        "in_progress": ("started", "spec.in_progress"),
        "in_review": ("started", "pr.merge"),
        "done": ("completed", "spec.done"),
        "rolled_back": ("completed", "spec.rolled_back"),
        "cancelled": ("cancelled", "spec.cancelled"),
        "bogus": ("backlog", "spec.draft"),  # a status the table does not know reads as a new Spec's
    }

    def test_a_spec_has_the_group_and_the_step_of_its_status(self):
        for st, (group, step) in self.SPEC.items():
            with self.subTest(status=st):
                self.write("specs/SPEC-1.md", spec("SPEC-1", st, "route: normal"))
                item = self.items(include_done=True)["SPEC-1"]
                self.assertEqual((item["group"], item["next"]["code"]), (group, step))

    def test_only_a_status_past_approval_needs_who_approved_it(self):
        for st in [*self.SPEC, "[draft]"]:
            with self.subTest(status=st):
                self.write("specs/SPEC-1.md", spec("SPEC-1", st, "route: normal"))
                _, warnings = validation.check_repo(self.root)
                self.assertEqual(any("no approved_by says who approved it" in w for w in warnings), st in status.PAST_APPROVAL)

    def test_an_intent_is_closed_by_a_person_and_made_active_by_its_slices(self):
        slices = "phases: [{id: P1, name: p, specs: [{id: SPEC-1, title: a}]}]\n"
        for stored, child, want in (
            ("draft", "draft", "draft"),
            ("draft", "in_progress", "active"),
            ("active", "draft", "draft"),
            ("done", "draft", "done"),
            ("cancelled", "in_progress", "cancelled"),
            ("bogus", "in_review", "active"),
        ):
            with self.subTest(stored=stored, child=child):
                self.write("product/intents/INTENT-1.md", intent("INTENT-1", "g", slices).replace("status: active\n", f"status: {stored}\n"))
                self.write("specs/SPEC-1.md", spec("SPEC-1", child, "parent: INTENT-1"))
                self.assertEqual(self.items(include_done=True)["INTENT-1"]["status"], want)

    def test_a_closed_intent_with_an_unfinished_slice_warns(self):
        slices = "phases: [{id: P1, name: p, specs: [{id: SPEC-1, title: a}]}]\n"
        for stored, child, warns in (
            ("done", "in_progress", True),
            ("done", "done", False),
            ("done", "cancelled", False),
            ("cancelled", "in_progress", False),
            ("active", "in_progress", False),
        ):
            with self.subTest(stored=stored, child=child):
                self.write("product/intents/INTENT-1.md", intent("INTENT-1", "g", slices).replace("status: active\n", f"status: {stored}\n"))
                self.write("specs/SPEC-1.md", spec("SPEC-1", child, "parent: INTENT-1"))
                _, warnings = validation.check_repo(self.root)
                self.assertEqual(any("not finished; reopen it or finish them" in w for w in warnings), warns)

    def test_a_proposal_is_in_the_group_its_status_table_gives(self):
        """`aidd status` puts each proposal in the group of its status (`x-groups`): a proposal not yet decided is in the backlog,
        one a person turned down or withdrew has stopped, and only a proposal in progress, or sent, is open work."""
        groups = {
            "qualifying": "backlog",
            "no_go": "cancelled",
            "drafting": "started",
            "signed_off": "started",
            "submitted": "started",
            "accepted": "completed",
            "rejected": "cancelled",
            "withdrawn": "cancelled",
        }
        self.assertEqual(groups, config.status_table("proposal")["x-groups"])
        for st, group in groups.items():
            with self.subTest(status=st):
                self.write("proposals/PROP-1/proposal.md", BASE.format(status=st, top=""))
                shown = self.items(include_done=True)["PROP-1"]
                self.assertEqual(shown["group"], group)
                self.assertEqual("PROP-1" in self.items(), group in workitems.OPEN_GROUPS)
        self.write("proposals/PROP-1/proposal.md", BASE.format(status="bogus", top=""))
        self.assertEqual(self.items(include_done=True)["PROP-1"]["group"], "backlog", "a status the table does not know is a new proposal's")

    def test_a_proposals_status_needs_the_decisions_on_record(self):
        withdrawn = 'outcome: {decision: withdrawn, by: "@lead", decided_on: "2026-09-25"}\n'
        rejected = ACCEPTED.replace("accepted", "rejected")
        for st, top, ok in (
            ("qualifying", "", True),
            ("no_go", "", False),
            ("drafting", "", False),
            ("drafting", GO, True),
            ("signed_off", GO, False),
            ("signed_off", GO + SIGNED, True),
            ("submitted", GO + SIGNED, False),
            ("submitted", GO + SIGNED + SUBMITTED, True),
            ("accepted", GO + SIGNED, False),
            ("accepted", GO + SIGNED + ACCEPTED, True),
            ("rejected", GO + SIGNED + rejected, True),
            ("withdrawn", "", False),
            ("withdrawn", withdrawn, True),
        ):
            with self.subTest(status=st, decisions=top):
                self.assertEqual(load(st, top)[2] == [], ok)


@functools.cache
def own_lists() -> dict[str, list[str]]:
    """Each place under src/aidd where a tuple, list, set, or dict of string keys holds two or more statuses of one table and
    nothing else, as `path:line` with the words."""
    tables = [set(table(t)["enum"]) for t in TYPES]
    found: dict[str, list[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Tuple | ast.List | ast.Set):
                words = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                whole = len(words) == len(node.elts)
            elif isinstance(node, ast.Dict):
                words = [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
                whole = len(words) == len(node.keys)
            else:
                continue
            if whole and len(set(words)) >= 2 and any(set(words) <= enum for enum in tables):
                found[f"{path.relative_to(ROOT).as_posix()}:{node.lineno}"] = words
    return found


class NoModuleKeepsAListOfStatuses(unittest.TestCase):
    def test_no_module_holds_its_own_list(self):
        mine = {k: v for k, v in own_lists().items() if k.partition(":")[0] not in OWN_LISTS}
        self.assertEqual(mine, {}, "read the status table (`config.status_set`) or add the set to `x-sets`")

    def test_each_exception_still_holds_a_list(self):
        held = {k.partition(":")[0] for k in own_lists()}
        self.assertEqual(set(OWN_LISTS) - held, set(), "an exception that no longer holds a list is removed")


if __name__ == "__main__":
    unittest.main()
