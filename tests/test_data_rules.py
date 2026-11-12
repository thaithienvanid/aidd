"""The six data rules of the loop's design (R1-R6) and the vocabulary rules of sections 4.1, 5.1, and 8.1 (V1-V4).

Each rule walks every property of every `schemas/*.schema.json` and of `schemas/editor/config.json`, with the walk of
tests/schema_walk.py (tests/data_rules.py). What a machine can decide, it decides; the rest is a judged list in
tests/fixtures/design/data_rules/judged.json. Today's schemas break some rules, and each break is one dated entry in
tests/fixtures/design/data_rules/exceptions.json with the package and (for V1-V4) the section 12 Task that removes it.
Rules 4, 5, and 6 of section 4.1 (the way back, the next line, and the printed line) need data that Task N6 adds, so they are left out.
The meanings of section 8.1 become data with Task N6 too, so V3 holds only what the schemas state until then. A Task that removes an
exception deletes its row and lowers that rule's count in `CEILINGS`, in the same change, so the list cannot grow back.
"""

import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts src on sys.path)
from helpers import ROOT

import data_rules as dr
import graph_cases as lc

# How many exceptions each rule has. A package or Task that fixes a break deletes the entry and lowers the number here;
# a new entry for a new break raises it, on purpose, with its reason in the change.
CEILINGS = {"R1": 9, "R2": 3, "R3": 25, "R4": 0, "R5": 57, "R6": 1, "V1": 7, "V2": 3, "V3": 4, "V4": 16}
PACKAGES = set(dr.packages()) - {"today"}
ENTRY_KEYS = {"rule", "where", "reason", "until", "listed_on"}
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SCHEMAS = dr.load_schemas()
JUDGED = dr.load_json("judged.json")
EXCEPTIONS = dr.load_json("exceptions.json")
FOUND = {rule: dr.breaks(rule, SCHEMAS, JUDGED) for rule in dr.RULES}
TASKS = set(JUDGED["tasks"])
DATE = {"$ref": "urn:aidd:1:common#/$defs/date"}
IDENTITY = {"$ref": "urn:aidd:1:common#/$defs/identity"}
INSTANT = {"type": "string", "format": "date-time"}


def seeded(change) -> dict[str, dict]:
    """A copy of every schema, in memory, that `change(schemas)` edits: the tracked files stay as they are."""
    scratch = copy.deepcopy(SCHEMAS)
    change(scratch)
    return scratch


def add_to(file: str, pointer: tuple[str, ...], **named):
    """A change that puts the named properties under `pointer` of `file`."""

    def change(schemas):
        target = schemas[file]
        for key in pointer:
            target = target[key]
        target.setdefault("properties", {}).update(named)

    return change


def new_breaks(rule: str, change, judged=JUDGED) -> set[str]:
    """The breaks a change to a scratch copy adds to the rule's own."""
    return set(dr.breaks(rule, seeded(change), judged)) - set(FOUND[rule])


class TheList(unittest.TestCase):
    def test_each_entry_names_its_rule_place_reason_package_and_day(self):
        for entry in EXCEPTIONS:
            is_vocab = str(entry.get("rule", "")).startswith("V")
            self.assertEqual(set(entry), ENTRY_KEYS | {"task"} if is_vocab else ENTRY_KEYS, entry)
            self.assertIn(entry["rule"], dr.RULES, entry)
            self.assertRegex(entry["where"], r"^[a-z-]+\.schema\.json#/", entry)
            self.assertTrue(entry["reason"].strip(), entry)
            self.assertIn(entry["until"], PACKAGES, entry)
            if is_vocab:
                self.assertIn(entry["task"], TASKS, entry)
            self.assertRegex(entry["listed_on"], DAY, entry)

    def test_every_package_an_entry_waits_on_is_described_and_none_waits_on_no_package(self):
        self.assertTrue(all(what.strip() for what in dr.packages().values()))
        self.assertEqual(list(dr.packages())[:6], ["today", "C2", "C3", "C4", "C5", "C6"], "the packages are in the order they land")
        self.assertNotIn("unassigned", dr.packages())
        for entry in EXCEPTIONS:
            self.assertIn(entry["until"], dr.packages(), entry)

    def test_no_place_is_listed_twice_for_one_rule(self):
        keys = [(e["rule"], e["where"]) for e in EXCEPTIONS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_the_list_only_shrinks(self):
        counts = {rule: sum(e["rule"] == rule for e in EXCEPTIONS) for rule in dr.RULES}
        self.assertEqual(counts, CEILINGS, "a rule's count is its ceiling: lower it when an exception goes, raise it only on purpose")

    def test_an_exception_whose_package_has_landed_fails(self):
        landed = set(lc.READERS) - {"today"}
        self.assertEqual([e for e in EXCEPTIONS if e["until"] in landed], [], "a package with a reader deletes the exceptions it removes")
        pretend = [dict(EXCEPTIONS[0], until="C4")]
        self.assertTrue(landed_problems(pretend, {"C4"}))
        self.assertEqual(landed_problems(pretend, {"C5"}), [])

    def test_the_walk_reaches_every_schema_and_the_editor_copy(self):
        expected = {p.name for p in (ROOT / "schemas").glob("*.schema.json")} | {dr.EDITOR}
        self.assertEqual(set(SCHEMAS), expected)
        self.assertGreater(len(list(dr.properties(SCHEMAS))), 1700)
        self.assertEqual(dr.source_of(f"{dr.EDITOR}#/properties/delegation"), "config.schema.json#/properties/delegation")
        self.assertEqual(dr.source_of(f"{dr.EDITOR}#/$defs/risks.area/properties/x"), "risks.schema.json#/$defs/area/properties/x")

    def test_every_judged_place_exists_and_every_allowance_still_applies(self):
        here = {p.where for p in dr.properties(SCHEMAS)}
        for where in [*JUDGED["R1"]["stored_status_words"], *JUDGED["R1"]["read_values"], *JUDGED["R2"]["several_questions"]]:
            self.assertIn(where, here, f"{where} is gone: drop it from judged.json")
        enums = dict(dr.enum_values(SCHEMAS))
        for where, reason in JUDGED["R2"]["contained_ok"].items():
            self.assertTrue(reason.strip(), where)
            self.assertTrue(dr.containing(enums.get(where, [])), f"{where} holds no contained value now: drop its allowance")
        for name in JUDGED["outputs"]:
            self.assertIn(name, SCHEMAS)
        without = {**JUDGED, "R3": {**JUDGED["R3"], "participle_flags": {}}}
        for name, reason in JUDGED["R3"]["participle_flags"].items():
            self.assertTrue(reason.strip(), name)
            narrowed = {**JUDGED["R3"], "participle_flags": {k: v for k, v in JUDGED["R3"]["participle_flags"].items() if k != name}}
            self.assertTrue(set(dr.breaks("R3", SCHEMAS, {**JUDGED, "R3": narrowed})) - set(FOUND["R3"]), f"`{name}` excuses no boolean now: drop it")
        self.assertTrue(set(dr.breaks("R3", SCHEMAS, without)) - set(FOUND["R3"]))
        for where in JUDGED["R6"]["child_list_places"]:
            self.assertIn(where, here, f"{where} is gone: drop it from judged.json")
        for table in (JUDGED["R5"]["links"], JUDGED["R5"]["one_meaning"], JUDGED["R4"]["dimensions"]):
            self.assertTrue(table)
        discovered_with_ruled_out = dr.status_enums(SCHEMAS, JUDGED, include_ruled_out=True)
        for where, reason in JUDGED["V1"]["ruled_out_statuses"].items():
            self.assertIn(where, discovered_with_ruled_out, f"{where} is no status enum candidate now: drop it from judged.json")
            self.assertTrue(reason.strip(), where)
        self.assertTrue(JUDGED["V4"]["other_shapes"])
        for name, item in JUDGED["V4"]["other_shapes"].items():
            self.assertTrue(item["reason"].strip(), name)
            if "choice_of" in item:
                self.assertIn(item["choice_of"].rsplit("/", 1)[1], JUDGED["V4"]["decision_keys"], f"{name} is a choice of a decision key")
            if not item["schema_places"] and "choice_of" not in item:
                self.assertTrue(item["why_no_place"].strip(), f"{name} holds no place, so the data says why")

    def test_every_key_judged_as_no_decision_and_no_status_is_still_found_by_its_rule_and_says_why(self):
        found_keys = {prop.key for prop in dr.loose_keys(SCHEMAS, JUDGED, include_judged_out=True).values()}
        for name, reason in JUDGED["V4"]["not_decisions"].items():
            self.assertTrue(reason.strip(), name)
            self.assertIn(name, found_keys, f"`{name}` is no key the rule finds now: drop it from judged.json")
        for name, reason in JUDGED["V1"]["other_enum_keys"].items():
            self.assertTrue(reason.strip(), name)
            self.assertTrue(dr.other_enum_keys(SCHEMAS, JUDGED)[name], f"no enum sits under `{name}` now: drop it from judged.json")

    def test_a_failure_names_its_rule_and_its_place_for_each_vocabulary_rule(self):
        place = "widget.schema.json#/properties/seeded"
        for rule in ("V1", "V2", "V3", "V4"):
            unlisted = dr.compare(rule, {**FOUND[rule], place: "seeded"}, EXCEPTIONS)
            self.assertEqual([line for line in unlisted if place in line and line.startswith(f"{rule}:")], unlisted[-1:], rule)
            ghost = {"rule": rule, "where": place, "reason": "r", "until": "C7", "task": "N6", "listed_on": "2026-11-14"}
            stale = dr.compare(rule, FOUND[rule], [*EXCEPTIONS, ghost])
            self.assertEqual([line for line in stale if place in line and line.startswith(f"{rule}:")], stale[-1:], rule)


def reason_problems(table: dict[str, str]) -> list[str]:
    return [f"{where}: a decided candidate needs a reason" for where, reason in table.items() if not reason.strip()]


def landed_problems(exceptions: list[dict], landed: set[str]) -> list[str]:
    return [f"{e['where']} waits on {e['until']}, which has landed: delete it" for e in exceptions if e["until"] in landed]


class OneRule:
    """What every rule's test does: its breaks are the listed ones, and each way to get that wrong fails."""

    rule = ""
    seed = None  # a change that adds one break the rule must find, and the place it is found at
    seed_where = ""

    def test_the_breaks_are_exactly_the_listed_exceptions(self):
        self.assertEqual(dr.compare(self.rule, FOUND[self.rule], EXCEPTIONS), [])

    def test_removing_one_exception_fails_the_check_and_adding_it_back_passes(self):
        mine = [e for e in EXCEPTIONS if e["rule"] == self.rule]
        for entry in mine:
            fewer = [e for e in EXCEPTIONS if e is not entry]
            (problem,) = dr.compare(self.rule, FOUND[self.rule], fewer)
            self.assertIn(entry["where"], problem)
            self.assertEqual(dr.compare(self.rule, FOUND[self.rule], fewer + [entry]), [])

    def test_an_exception_for_a_break_that_is_gone_fails(self):
        ghost = {"rule": self.rule, "where": "spec.schema.json#/properties/no_longer_here", "reason": "r", "until": "C2", "listed_on": "2026-11-13"}
        (problem,) = dr.compare(self.rule, FOUND[self.rule], [*EXCEPTIONS, ghost])
        self.assertIn("no longer breaks", problem)

    def test_a_new_break_in_a_scratch_copy_is_found(self):
        scratch = seeded(self.seed)
        new = dr.breaks(self.rule, scratch, JUDGED)
        self.assertEqual(set(new) - set(FOUND[self.rule]), {self.seed_where}, "the seeded break is the only new place")
        (problem,) = dr.compare(self.rule, new, EXCEPTIONS)
        self.assertIn(self.seed_where, problem)


class R1StoredOnce(OneRule, unittest.TestCase):
    rule = "R1"
    seed = staticmethod(add_to("spec.schema.json", (), tasks_count={"type": "integer"}))
    seed_where = "spec.schema.json#/properties/tasks_count"

    def test_a_stored_status_the_judged_list_does_not_name_is_a_break(self):
        change = add_to("spec.schema.json", ("$defs", "task"), status={"enum": ["open", "closed"]})
        self.assertEqual(new_breaks("R1", change), {"spec.schema.json#/$defs/task/properties/status"})

    def test_a_word_a_file_may_not_store_is_a_break_and_a_word_it_may_is_not(self):
        change = lambda schemas: schemas["spec.schema.json"]["properties"].__setitem__("status", {"enum": ["draft", "built", "merged"]})  # noqa: E731
        self.assertEqual(new_breaks("R1", change), {"spec.schema.json#/properties/status/enum/merged"})


class R2OneQuestion(OneRule, unittest.TestCase):
    rule = "R2"
    seed = staticmethod(
        lambda schemas: schemas["common.schema.json"]["$defs"].__setitem__("seeded_coverage", {"enum": ["agent", "agent_person_decides", "person"]})
    )
    seed_where = "common.schema.json#/$defs/seeded_coverage"

    def test_a_value_that_contains_another_value_of_its_own_enum_is_a_break_in_the_field_it_was_found_in(self):
        change = add_to("spec.schema.json", (), who_decides={"enum": ["agents", "agents_person_decides", "humans"]})
        self.assertEqual(new_breaks("R2", change), {"spec.schema.json#/properties/who_decides"})

    def test_a_product_of_two_vocabularies_other_things_own_is_a_break_and_a_plain_pair_is_not(self):
        joined = {"enum": ["spec.approve", "spec.done", "intent.approve", "intent.done"]}
        self.assertEqual(new_breaks("R2", add_to("spec.schema.json", (), step=joined)), {"spec.schema.json#/properties/step"})
        plain = {"enum": ["latest_lts", "current_stable", "current_major", "pinned"]}
        self.assertEqual(new_breaks("R2", add_to("spec.schema.json", (), policy=plain)), set(), "a choice no other schema owns the parts of is no product")
        actions = {"enum": ["git.push", "git.merge", "pr.merge", "spec.approve"]}
        self.assertEqual(new_breaks("R2", add_to("spec.schema.json", (), asks=actions)), set(), "action ids are `resource.verb`, which the risk rules own")


class R3OneObject(OneRule, unittest.TestCase):
    rule = "R3"
    seed = staticmethod(add_to("spec.schema.json", (), accepted_by={"type": "string"}, accepted_at={"type": "string", "format": "date-time"}))
    seed_where = "spec.schema.json#/properties/accepted_by"

    def test_a_who_found_by_its_name_or_as_an_agent_noun_beside_its_event_is_a_loose_pair(self):
        self.assertEqual(
            new_breaks("R3", add_to("spec.schema.json", (), approver={"type": "string"}, approved_on=DATE)), {"spec.schema.json#/properties/approver"}
        )
        self.assertEqual(
            new_breaks("R3", add_to("spec.schema.json", (), signed_by={"type": "string"}, signed={"type": "string"})),
            {"spec.schema.json#/properties/signed_by"},
        )
        self.assertEqual(new_breaks("R3", add_to("spec.schema.json", (), owner={"type": "string"}, owned_on=DATE)), set(), "a role noun is no loose pair")

    def test_a_decision_object_is_the_one_shared_definition_and_absent_until_it_happened(self):
        ref = {"$ref": "urn:aidd:1:common#/$defs/decision"}
        for key in ("approval", "cancellation"):
            self.assertEqual(new_breaks("R3", add_to("spec.schema.json", (), **{key: ref})), set(), key)
            self.assertEqual(new_breaks("R3", add_to("spec.schema.json", (), **{key: {"allOf": [ref]}})), set(), f"{key} that adds to the definition")
            self.assertEqual(new_breaks("R3", add_to("spec.schema.json", (), **{key: {"type": "object"}})), {f"spec.schema.json#/properties/{key}"}, key)
            other = {"$ref": "urn:aidd:1:common#/$defs/emergency"}
            self.assertEqual(
                new_breaks("R3", add_to("spec.schema.json", (), **{key: other})), {f"spec.schema.json#/properties/{key}"}, f"{key} of another definition"
            )

        def required(schemas):
            add_to("spec.schema.json", (), approval=ref)(schemas)
            schemas["spec.schema.json"]["required"].append("approval")

        self.assertEqual(new_breaks("R3", required), {"spec.schema.json#/properties/approval"})

    def test_a_true_or_false_that_records_an_event_is_a_break_whatever_its_name_and_the_judged_list_excuses_the_rest(self):
        for name in ("reviewed", "deployed", "verified", "manual_signoff", "go_no_go_given"):
            found = new_breaks("R3", add_to("spec.schema.json", (), **{name: {"type": "boolean"}}))
            self.assertEqual(found, {f"spec.schema.json#/properties/{name}"} if name in ("reviewed", "deployed", "verified", "go_no_go_given") else set(), name)
        beside_a_fact = add_to("spec.schema.json", (), deployed={"type": "boolean"}, deployed_at={"type": "string", "format": "date-time"})
        self.assertEqual(new_breaks("R3", beside_a_fact), {"spec.schema.json#/properties/deployed"}, "a flag beside its own when still has no who")
        self.assertEqual(new_breaks("R3", add_to("spec.schema.json", (), shared={"type": "boolean"})), set(), "an excused name passes")


class R4Collection(OneRule, unittest.TestCase):
    rule = "R4"
    seed = staticmethod(
        add_to("spec.schema.json", (), minor_reviewers={"type": "array"}, normal_reviewers={"type": "array"}, major_reviewers={"type": "array"})
    )
    seed_where = "spec.schema.json#"

    def test_a_map_with_an_entry_for_each_value_of_a_dimension_whose_members_are_objects_is_a_break(self):
        member = {"type": "object", "properties": {"url": {"type": "string"}}}
        change = add_to("spec.schema.json", (), by_environment={"type": "object", "properties": {e: member for e in ("sandbox", "staging", "production")}})
        self.assertEqual(new_breaks("R4", change), {"spec.schema.json#/properties/by_environment"})
        keyed = {"type": "object", "propertyNames": {"enum": ["minor", "normal", "major"]}, "additionalProperties": member}
        self.assertEqual(new_breaks("R4", add_to("spec.schema.json", (), by_route=keyed)), {"spec.schema.json#/properties/by_route"})

    def test_a_map_keyed_by_id_whose_members_are_looked_up_by_key_is_no_break(self):
        for member in ({"type": "string"}, {"type": "integer"}, {"type": "array"}):
            change = add_to("spec.schema.json", (), looked_up={"type": "object", "properties": {r: member for r in ("minor", "normal", "major")}})
            self.assertEqual(new_breaks("R4", change), set(), member)

    def test_what_the_schemas_hold_today_breaks_nothing_and_a_few_names_are_no_dimension(self):
        self.assertEqual(FOUND["R4"], {})
        change = add_to("spec.schema.json", (), minor_reviewers={"type": "array"}, normal_reviewers={"type": "array"})
        self.assertEqual(new_breaks("R4", change), set(), "two values are not a dimension")


class R5OneShape(OneRule, unittest.TestCase):
    rule = "R5"
    seed = staticmethod(add_to("spec.schema.json", (), shipped_date={"type": "string"}))
    seed_where = "spec.schema.json#/properties/shipped_date"

    def test_each_family_is_checked(self):
        instant = {"type": "string", "format": "date-time"}
        cases = {
            "an instant that is not `_at`": ("handed_over", instant),
            "a `_on` that holds no day": ("handed_on", {"type": "string"}),
            "a unit in the name with no number": ("wait_days", {"type": "string"}),
            "a duration as text": ("wait", {"type": "string", "pattern": "^[0-9]+[mhd]$"}),
            "who outside its object": ("signed_by", IDENTITY),
            "who by name with no identity": ("accepted_by", {"type": "string"}),
            "a link with another name": ("belongs_to_intent", {"$ref": "urn:aidd:1:common#/$defs/id"}),
            "a day named `_at`": ("opened_at", DATE),
            "a name that ends in `_time`": ("sent_time", instant),
            "a name that ends in `_day`": ("due_day", DATE),
            "a commit named for what it is": ("review_sha", {"type": "string", "pattern": "^[0-9a-f]{7,40}$", "$ref": "urn:aidd:1:common#/$defs/sha"}),
            "a commit with a name that ends in commit": ("reviewed_commit", {"type": "string"}),
        }
        for label, (name, node) in cases.items():
            self.assertEqual(new_breaks("R5", add_to("spec.schema.json", (), **{name: node})), {f"spec.schema.json#/properties/{name}"}, label)

    def test_one_word_has_one_meaning(self):
        for name, node in (("outcome", {"type": "object"}), ("approval", {"type": "string"}), ("cancellation", {"type": "boolean"})):
            self.assertEqual(new_breaks("R5", add_to("intent.schema.json", (), **{name: node})), {f"intent.schema.json#/properties/{name}"}, name)
        self.assertEqual(new_breaks("R5", add_to("intent.schema.json", (), outcome={"type": "string"})), set(), "an Intent's outcome is one sentence")

    def test_a_qualifier_joined_onto_a_plain_word_is_found_where_the_plain_word_is_free_and_not_where_it_is_taken(self):
        found = new_breaks("R5", add_to("spec.schema.json", (), review_action={"$ref": "#/$defs/action_id"}))
        self.assertEqual(found, {"spec.schema.json#/properties/review_action"})
        why = dr.qualified(seeded(add_to("spec.schema.json", (), review_action={"type": "string"})))["spec.schema.json#/properties/review_action"]
        self.assertIn("`action` is free in this parent", why)
        beside = add_to("spec.schema.json", (), review_action={"type": "string"}, action={"type": "string"})
        self.assertEqual(new_breaks("R5", beside), set(), "where `action` is taken, a qualifier may be needed, and a person judges")

    def test_the_area_names_its_action_by_the_plain_word(self):
        """A risk area's key for the action a person's yes covers is `action`, as `next.action` and a rule's own `action` are, in the
        schema and its editor copy, and the walk finds nothing in the area."""
        scratch = dr.breaks("R5", SCHEMAS, JUDGED)
        self.assertEqual(set(scratch) - set(FOUND["R5"]), set())
        for props in (SCHEMAS["risks.schema.json"]["$defs"]["area"]["properties"], SCHEMAS[dr.EDITOR]["$defs"]["risks.area"]["properties"]):
            self.assertIn("action", props)
            self.assertNotIn("approval", props)
        self.assertEqual({w for w in scratch if "/area/properties/" in w}, set())

    def test_a_name_that_begins_or_ends_with_its_parent_or_its_schema_is_a_candidate(self):
        for name in ("spec_flag", "flag_spec"):
            self.assertEqual(new_breaks("R5", add_to("spec.schema.json", (), **{name: {"type": "string"}})), {f"spec.schema.json#/properties/{name}"}, name)
        inside = add_to("spec.schema.json", ("$defs", "task"), task_note={"type": "string"})
        self.assertEqual(new_breaks("R5", inside), {"spec.schema.json#/$defs/task/properties/task_note"})

    def test_an_enum_value_with_a_free_plain_word_is_a_candidate(self):
        self.assertEqual(
            new_breaks("R5", add_to("spec.schema.json", (), stage={"enum": ["merge_state", "open"]})), {"spec.schema.json#/properties/stage/enum/merge_state"}
        )
        self.assertEqual(new_breaks("R5", add_to("spec.schema.json", (), stage={"enum": ["merge_state", "state"]})), set())

    def test_every_decided_candidate_has_a_reason_and_still_applies_and_the_rest_are_exceptions(self):
        kept = JUDGED["R5"]["qualified_kept"]
        self.assertNotIn("qualified_open", JUDGED["R5"], "no candidate stays open: it is kept with a reason, or an exception with a package")
        now = {dr.source_of(w) for w in dr.qualified(SCHEMAS)}
        for where in kept:
            self.assertIn(where, now, f"{where} is no candidate now: drop it from judged.json")
        self.assertEqual(reason_problems(kept), [])
        listed = {e["where"] for e in EXCEPTIONS if e["rule"] == "R5"}
        self.assertEqual(now - set(kept), now & listed, "each candidate that is not kept is an exception with a package")
        some = next(iter(kept))
        self.assertTrue(reason_problems({**kept, some: "  "}), "a kept entry with an empty reason fails")
        self.assertTrue(reason_problems({**kept, some: ""}))
        for entry in EXCEPTIONS:
            self.assertNotIn("the lead decides", entry["reason"], entry["where"])

    def test_a_candidate_in_neither_list_fails(self):
        change = add_to("spec.schema.json", (), quick_reason={"type": "string"})
        self.assertEqual(new_breaks("R5", change), {"spec.schema.json#/properties/quick_reason"})
        decided = {
            **JUDGED,
            "R5": {**JUDGED["R5"], "qualified_kept": {**JUDGED["R5"]["qualified_kept"], "spec.schema.json#/properties/quick_reason": "a reason"}},
        }
        self.assertEqual(new_breaks("R5", change, decided), set(), "a kept entry with a reason lets it land")

    def test_the_names_the_families_allow_pass(self):
        ok = {
            "released_at": {"type": "string", "format": "date-time"},
            "measured_on": DATE,
            "review_due": DATE,
            "wait_seconds": {"type": "integer"},
            "from": {"$ref": "urn:aidd:1:common#/$defs/id"},
            "commit": {"type": "string"},
            "head_sha": {"type": "string"},
            "blocked_by": {"$ref": "urn:aidd:1:common#/$defs/id"},
        }
        self.assertEqual(new_breaks("R5", add_to("spec.schema.json", (), **ok)), set())


class R6ChildNamesParent(OneRule, unittest.TestCase):
    rule = "R6"
    seed = staticmethod(add_to("intent.schema.json", (), specs={"type": "array", "items": {"$ref": "urn:aidd:1:common#/$defs/id"}}))
    seed_where = "intent.schema.json#/properties/specs"

    def test_a_link_kept_at_both_ends_is_a_break(self):
        both = add_to("spec.schema.json", (), fills={"type": "array", "items": {"type": "string"}}, filled_by={"type": "array", "items": {"type": "string"}})
        self.assertEqual(new_breaks("R6", both), {"spec.schema.json#/properties/filled_by"})

    def test_an_item_types_plural_is_a_list_of_children_only_where_its_parent_type_is_declared(self):
        children = {"type": "array", "items": {"type": "string"}}
        self.assertEqual(new_breaks("R6", add_to("spec.schema.json", (), specs=children)), set(), "a Spec is not the parent of Specs")
        self.assertEqual(new_breaks("R6", add_to("spec.schema.json", (), adrs=children)), set(), "an ADR has no parent type")
        self.assertEqual(new_breaks("R6", add_to("intent.schema.json", (), specs=children)), {"intent.schema.json#/properties/specs"})

    def test_an_item_type_with_a_parent_type_has_a_parent_property(self):
        def lose(schemas):
            del schemas["spec.schema.json"]["properties"]["parent"]

        self.assertIn("spec.schema.json#/properties/parent", new_breaks("R6", lose))


class ScratchFiles(unittest.TestCase):
    def test_a_break_seeded_into_a_copy_of_a_schema_file_on_disk_is_found_and_the_tracked_file_is_unchanged(self):
        before = (ROOT / "schemas" / "spec.schema.json").read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "schemas"
            (folder / "editor").mkdir(parents=True)
            for path in (ROOT / "schemas").glob("*.schema.json"):
                (folder / path.name).write_bytes(path.read_bytes())
            (folder / "editor" / "config.json").write_bytes((ROOT / "schemas" / "editor" / "config.json").read_bytes())
            spec = json.loads((folder / "spec.schema.json").read_text(encoding="utf-8"))
            spec["properties"]["approved_on"] = {"type": "string"}
            (folder / "spec.schema.json").write_text(json.dumps(spec), encoding="utf-8")
            new = dr.breaks("R5", dr.load_schemas(Path(tmp)), JUDGED)
        self.assertEqual(set(new) - set(FOUND["R5"]), {"spec.schema.json#/properties/approved_on"})
        self.assertEqual((ROOT / "schemas" / "spec.schema.json").read_bytes(), before)


def _with_decision_def(change=None):
    def apply(schemas):
        schemas["common.schema.json"]["$defs"]["decision"] = {
            "type": "object",
            "properties": {"by": IDENTITY, "at": {"type": "string", "format": "date-time"}},
        }
        if change is not None:
            change(schemas)

    return apply


class V1StatusGroups(OneRule, unittest.TestCase):
    """Rules 1-3 of section 4.1, section 8.1, and section 5.1. Rules 4, 5, and 6 of section 4.1 need data that Task N6 adds, so they are left out."""

    rule = "V1"
    seed = staticmethod(
        lambda schemas: schemas.__setitem__(
            "newtype.schema.json",
            {"properties": {"status": {"enum": ["fresh", "settled"]}}},
        )
    )
    seed_where = "newtype.schema.json#/properties/status"

    def test_every_status_needs_one_valid_group_and_a_new_type_with_valid_groups_passes(self):
        cases = [
            ("missing group map", {"enum": ["alpha", "beta"]}, {"spec.schema.json#/$defs/seeded/properties/status"}),
            (
                "missing status word in x-groups",
                {"enum": ["alpha", "beta"], "x-groups": {"alpha": "backlog"}},
                {"spec.schema.json#/$defs/seeded/properties/status/x-groups/beta"},
            ),
            ("invalid group name", {"enum": ["alpha"], "x-groups": {"alpha": "closed"}}, {"spec.schema.json#/$defs/seeded/properties/status/x-groups/alpha"}),
            (
                "multi-group list",
                {"enum": ["alpha"], "x-groups": {"alpha": ["backlog", "started"]}},
                {"spec.schema.json#/$defs/seeded/properties/status/x-groups/alpha"},
            ),
            (
                "extra key in x-groups",
                {"enum": ["alpha"], "x-groups": {"alpha": "backlog", "ghost": "done"}},
                {"spec.schema.json#/$defs/seeded/properties/status/x-groups/ghost"},
            ),
            ("valid five-group mapping", {"enum": ["alpha", "beta"], "x-groups": {"alpha": "backlog", "beta": "cancelled"}}, set()),
        ]
        for label, status_node, expected in cases:
            change = lambda schemas, s=status_node: schemas["spec.schema.json"]["$defs"].__setitem__("seeded", {"properties": {"status": s}})  # noqa: E731
            self.assertEqual(new_breaks("V1", change), expected, label)

    def test_a_status_enum_is_found_flat_wrapped_in_a_choice_or_behind_a_ref_and_other_keys_are_no_status(self):
        enum = {"type": "string", "enum": ["alpha", "beta"]}
        wrapped = {
            "allOf": {"allOf": [enum]},
            "anyOf": {"anyOf": [enum, {"type": "null"}]},
            "oneOf": {"oneOf": [enum]},
        }
        for kind, node in wrapped.items():
            change = lambda schemas, n=node: schemas.__setitem__("widget.schema.json", {"properties": {"status": n}})  # noqa: E731
            index = 0
            self.assertEqual(new_breaks("V1", change), {f"widget.schema.json#/properties/status/{kind}/{index}"}, kind)
            closed = lambda schemas, k=kind: schemas.__setitem__(  # noqa: E731
                "widget.schema.json", {"properties": {"status": {k: [{"enum": ["draft", "closed"]}]}}}
            )
            self.assertEqual(new_breaks("V2", closed), {f"widget.schema.json#/properties/status/{kind}/0/enum/closed"}, kind)

        def behind_a_ref(schemas):
            schemas["common.schema.json"]["$defs"]["seeded_status"] = {"enum": ["alpha"]}
            schemas["widget.schema.json"] = {"properties": {"status": {"allOf": [{"$ref": "urn:aidd:1:common#/$defs/seeded_status"}]}}}

        self.assertEqual(new_breaks("V1", behind_a_ref), {"common.schema.json#/$defs/seeded_status"})
        for key in JUDGED["V1"]["other_enum_keys"]:
            other = lambda schemas, k=key: schemas.__setitem__("widget.schema.json", {"properties": {k: enum}})  # noqa: E731
            self.assertEqual(dr.breaks("V1", seeded(other), JUDGED), FOUND["V1"], f"`{key}` is no status")


class V2NoFrameOrGroupWords(OneRule, unittest.TestCase):
    rule = "V2"
    seed = staticmethod(add_to("postmortem.schema.json", (), status={"enum": ["draft", "closed", "published"]}))
    seed_where = "postmortem.schema.json#/properties/status/enum/closed"

    def test_frame_words_and_group_words_fail_except_cancelled(self):
        cases = [
            ("open", {"postmortem.schema.json#/properties/status/enum/open"}),
            ("closed", {"postmortem.schema.json#/properties/status/enum/closed"}),
            ("reopened", {"postmortem.schema.json#/properties/status/enum/reopened"}),
            ("backlog", {"postmortem.schema.json#/properties/status/enum/backlog"}),
            ("unstarted", {"postmortem.schema.json#/properties/status/enum/unstarted"}),
            ("started", {"postmortem.schema.json#/properties/status/enum/started"}),
            ("completed", {"postmortem.schema.json#/properties/status/enum/completed"}),
            ("cancelled", set()),
        ]
        for word, expected in cases:
            change = add_to("postmortem.schema.json", (), status={"enum": ["draft", word, "published"]})
            self.assertEqual(new_breaks("V2", change), expected, word)


class V3OneWordOneMeaning(OneRule, unittest.TestCase):
    rule = "V3"
    seed = staticmethod(
        add_to(
            "postmortem.schema.json",
            (),
            status={"enum": ["draft", "in_review", "published"], "x-groups": {"draft": "unstarted", "in_review": "started", "published": "completed"}},
        )
    )
    seed_where = "postmortem.schema.json#/properties/status/x-groups/draft"

    def test_shared_status_must_keep_one_group_and_one_x_meaning_across_types(self):
        conflicting_group = add_to(
            "postmortem.schema.json",
            (),
            status={"enum": ["draft", "published"], "x-groups": {"draft": "unstarted", "published": "completed"}},
        )
        self.assertIn("postmortem.schema.json#/properties/status/x-groups/draft", new_breaks("V3", conflicting_group))

        matching_group_and_meaning = add_to(
            "postmortem.schema.json",
            (),
            status={
                "enum": ["draft", "published"],
                "x-groups": {"draft": "backlog", "published": "completed"},
                "x-meanings": {"draft": "Same shared meaning.", "published": "Published."},
            },
        )
        # Matching Spec's group (`backlog`) while differing in `x-meanings` flags `x-meanings` only.
        breaks = new_breaks("V3", matching_group_and_meaning)
        self.assertIn("postmortem.schema.json#/properties/status/x-meanings/draft", breaks)
        self.assertNotIn("postmortem.schema.json#/properties/status/x-groups/draft", breaks)

        def aligned(schemas):
            for ptr in ("status", "intent_status"):
                schemas["common.schema.json"]["$defs"][ptr]["x-meanings"]["draft"] = "Being written."
            schemas["postmortem.schema.json"]["properties"]["status"] = {
                "enum": ["draft", "published"],
                "x-groups": {"draft": "backlog", "published": "completed"},
                "x-meanings": {"draft": "Being written.", "published": "Agreed."},
            }

        self.assertNotIn("postmortem.schema.json#/properties/status/x-meanings/draft", dr.breaks("V3", seeded(aligned), JUDGED))


class V4DecisionShape(OneRule, unittest.TestCase):
    rule = "V4"
    seed = staticmethod(add_to("spec.schema.json", (), cancellation={"type": "object"}))
    seed_where = "spec.schema.json#/properties/cancellation"

    def test_a_key_that_holds_who_or_when_is_found_by_its_form_and_a_key_judged_out_or_a_link_is_not(self):
        spec = "spec.schema.json#/properties/"
        cases = [
            ("a who with its when", add_to("spec.schema.json", (), signed_by=IDENTITY, signed_at=INSTANT), {spec + "signed_by"}),
            ("a who alone", add_to("spec.schema.json", (), signed_by=IDENTITY), {spec + "signed_by"}),
            ("a day with its who", add_to("spec.schema.json", (), vetted_by=IDENTITY, vetted_on=DATE), {spec + "vetted_by"}),
            (
                "a standing instant named for an event",
                add_to("postmortem.schema.json", (), approved_at=INSTANT),
                {"postmortem.schema.json#/properties/approved_at"},
            ),
            ("a standing day named for an event", add_to("spec.schema.json", (), signed_on=DATE), {spec + "signed_on"}),
            (
                "the four keys the design renames",
                add_to("spec.schema.json", (), decided_on=DATE, granted_by=IDENTITY, set_by=IDENTITY, revised_at=INSTANT),
                {spec + k for k in ("decided_on", "granted_by", "set_by", "revised_at")},
            ),
            ("a link", add_to("spec.schema.json", (), replaced_by={"$ref": "urn:aidd:1:common#/$defs/id"}), set()),
            ("a day that names no event and sits beside no who", add_to("postmortem.schema.json", (), starts_on=DATE, ends_on=DATE), set()),
            ("a day that names no event, beside a who", add_to("spec.schema.json", (), starts_on=DATE), {spec + "starts_on"}),
            ("a day beside a link only", add_to("postmortem.schema.json", (), blocked_by={"$ref": "urn:aidd:1:common#/$defs/id"}, start_on=DATE), set()),
            ("a name for an event that holds no day", add_to("spec.schema.json", (), approved_at={"type": "string"}), set()),
            ("the definition's own `at`", add_to("spec.schema.json", (), at=INSTANT), set()),
            ("a name judged out", add_to("spec.schema.json", (), started_at=INSTANT, checked_by=IDENTITY), set()),
        ]
        for label, change, expected in cases:
            self.assertEqual(new_breaks("V4", change), expected, label)
        without = {**JUDGED, "V4": {**JUDGED["V4"], "not_decisions": {}}}
        found = new_breaks("V4", add_to("spec.schema.json", (), started_at=INSTANT, checked_by=IDENTITY), without)
        self.assertLessEqual({spec + "started_at", spec + "checked_by"}, found, "a name the judged list does not hold is found")

    def test_an_object_that_holds_who_and_when_itself_is_a_break_unless_it_is_the_definition_or_a_listed_shape(self):
        by_and_at = {"type": "object", "properties": {"by": IDENTITY, "at": INSTANT}}
        beside_by = {"type": "object", "properties": {"by": IDENTITY, "approval_on": DATE}}
        written = {"type": "object", "properties": {"by": IDENTITY, "recorded_at": INSTANT}}
        spec = "spec.schema.json#/properties/"
        cases = [
            ("a new object with `by` and `at`", add_to("spec.schema.json", (), signoff=by_and_at), {spec + "signoff"}),
            (
                "a day under another name beside `by`",
                add_to("spec.schema.json", (), signoff=beside_by),
                {spec + "signoff", spec + "signoff/properties/approval_on"},
            ),
            ("a when that is judged out", add_to("spec.schema.json", (), signoff=written), set()),
            ("a listed shape", add_to("proposal.schema.json", (), answer=by_and_at), set()),
            ("the one definition", _with_decision_def(), set()),
            (
                "an object that refers to the definition and lists `by` and `at` again",
                _with_decision_def(add_to("spec.schema.json", (), signoff={**by_and_at, "allOf": [{"$ref": "urn:aidd:1:common#/$defs/decision"}]})),
                set(),
            ),
            (
                "an object that refers to the definition and holds a day under another name",
                _with_decision_def(add_to("spec.schema.json", (), signoff={**beside_by, "allOf": [{"$ref": "urn:aidd:1:common#/$defs/decision"}]})),
                {spec + "signoff/properties/approval_on"},
            ),
        ]
        for label, change, expected in cases:
            self.assertEqual(new_breaks("V4", change), expected, label)

    def test_the_objects_the_design_retires_or_reshapes_still_break_when_their_day_key_is_renamed_to_at(self):
        objects = {
            ("proposal.schema.json", "properties", "go_no_go"),
            ("proposal.schema.json", "properties", "sign_off"),
            ("proposal.schema.json", "properties", "outcome"),
            ("exploration.schema.json", "properties", "outcome"),
            ("spec.schema.json", "$defs", "triage"),
        }

        def rename(schemas):
            for file, *pointer in objects:
                node = schemas[file]
                for key in pointer:
                    node = node[key]
                node["properties"]["at"] = node["properties"].pop("decided_on")

        found = dr.breaks("V4", seeded(rename), JUDGED)
        for file, *pointer in objects:
            self.assertIn(f"{file}#/{'/'.join(pointer)}", found)
            self.assertNotIn(f"{file}#/{'/'.join(pointer)}/properties/decided_on", found)

    def test_table_1_decisions_refer_to_decision_def_alone_or_in_a_choice_and_a_choice_holds_nothing_else(self):
        ref = {"$ref": "urn:aidd:1:common#/$defs/decision"}
        delegate = {"type": "object", "properties": {"on_behalf_of": IDENTITY, "at": DATE, "delegate_answer": {"type": "string"}}}
        reason = {"type": "object", "properties": {"reason": {"type": "string"}}}
        spec = "spec.schema.json#/properties/"
        cases = [
            ("decline without ref", add_to("spec.schema.json", (), decline={"type": "object"}), {spec + "decline"}),
            (
                "exploration result without ref",
                add_to("exploration.schema.json", (), result={"type": "object"}),
                {"exploration.schema.json#/properties/result"},
            ),
            ("a list of decisions is no one decision", add_to("spec.schema.json", (), cancellation={"type": "array", "items": ref}), {spec + "cancellation"}),
            (
                "a choice with a branch of another shape",
                add_to("spec.schema.json", (), cancellation={"anyOf": [ref, {"type": "string"}]}),
                {spec + "cancellation/anyOf/1"},
            ),
            ("a choice of two decisions", add_to("spec.schema.json", (), cancellation={"oneOf": [ref, {"allOf": [ref, reason]}]}), set()),
            (
                "a delegate shape off a Spec's approval",
                add_to("spec.schema.json", (), cancellation={"anyOf": [ref, delegate]}),
                {spec + "cancellation/anyOf/1"},
            ),
            ("a Spec's approval: the decision and the delegate shape", add_to("spec.schema.json", (), approval={"anyOf": [ref, delegate]}), set()),
            (
                "a Spec's approval with a third branch",
                add_to("spec.schema.json", (), approval={"anyOf": [ref, delegate, {"type": "string"}]}),
                {spec + "approval/anyOf/2"},
            ),
            (
                "a delegate shape that also refers to the decision",
                add_to("spec.schema.json", (), approval={"oneOf": [ref, {"allOf": [ref], **delegate}]}),
                {spec + "approval/oneOf/1"},
            ),
            ("a cancellation with a reason", add_to("spec.schema.json", (), cancellation={"allOf": [ref, reason]}), set()),
            ("an exploration result with a decision", add_to("exploration.schema.json", (), result={"allOf": [ref, reason]}), set()),
        ]
        for label, change, expected in cases:
            self.assertEqual(new_breaks("V4", _with_decision_def(change)), expected, label)

    def test_table_2_other_shapes_cannot_pass_as_a_decision_alone_in_a_list_or_in_a_choice(self):
        ref = {"$ref": "urn:aidd:1:common#/$defs/decision"}

        def at(file, *pointer):
            def change(node):
                def apply(schemas):
                    target = schemas[file]
                    for key in pointer:
                        target = target[key]
                    target.update(node)

                return apply

            return change

        cases = [
            ("the answer", add_to("proposal.schema.json", (), answer=ref), "proposal.schema.json#/properties/answer"),
            (
                "revisions' entry",
                at("spec.schema.json", "properties", "revisions", "items")({"$ref": ref["$ref"]}),
                "spec.schema.json#/properties/revisions/items",
            ),
            (
                "revisions' entry in a choice",
                at("spec.schema.json", "properties", "revisions", "items")({"anyOf": [ref, {"type": "object"}]}),
                "spec.schema.json#/properties/revisions/items",
            ),
            (
                "a criterion's result",
                at("intent.schema.json", "$defs", "criterion", "properties", "result")({"$ref": ref["$ref"]}),
                "intent.schema.json#/$defs/criterion/properties/result",
            ),
            ("a scope item's results as a list", at("product-scope.schema.json", "$defs", "results", "items")(ref), "product-scope.schema.json#/$defs/results"),
            (
                "a requirement's results as a list",
                at("product-scope.schema.json", "$defs", "requirement_results", "items")(ref),
                "product-scope.schema.json#/$defs/requirement_results",
            ),
            (
                "a scope item's results as a ref",
                at("product-scope.schema.json", "$defs", "results")({"$ref": ref["$ref"]}),
                "product-scope.schema.json#/$defs/results",
            ),
        ]
        for label, change, expected in cases:
            self.assertIn(expected, new_breaks("V4", _with_decision_def(change)), label)


if __name__ == "__main__":
    unittest.main()
