"""schemas/lifecycles.json: one row for each thing that can be open, so nothing opens and never closes.

The invariant: every row has what closes it, who may close it, and what finds one left open, and no finder is "nobody".
Every type of schemas/item-types.json, and every key of the config, the handoff note, and the item types' schemas that
carries a date or a release, is a row or is listed as never open with its reason. A new date key, or a new type, fails
here until a person says how it closes. The gaps the audit found and fixed are held here too: an open RAID log entry past
its `due`, and a `waiting` stop past its `resumes_at`, each a warning of `aidd validate`."""

from __future__ import annotations

import datetime as dt
import re
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  # puts src/ on the path and makes the run hermetic
from helpers import make_repo

from aidd.cli import parser as cli_parser
from aidd.kernel import json_schema, resources
from aidd.workitems import due_dates, validation

TABLE = resources.load_json("lifecycles.json")
THINGS = TABLE["things"]
ITEM_TYPES = resources.load_json("item-types.json")["types"]
# A key whose name says it ends something, or holds something until a person releases it. A key with a date format is
# found by its format, so this list holds only the names that carry no date of their own.
RELEASE = re.compile(r"(^|_)(due|until|sunset|ends_on|timebox|hold|locks|locked|waivers|flags|waiting_on|blocked_by|open_decisions|stopped_at|resumes_at)$")
DATE_DEF = ("common.schema.json", "/$defs/date")


def _target(ref: str, home: str) -> tuple[str, str]:
    """The file and the pointer a `$ref` names, read from the schema `home`."""
    if ref.startswith("urn:aidd:1:"):
        name, _, pointer = ref.removeprefix("urn:aidd:1:").partition("#")
        return f"{name}.schema.json", pointer
    name, _, pointer = ref.partition("#")
    return name or home, pointer


def _node(home: str, pointer: str) -> object:
    node: object = resources.load_json(home)
    for part in [p for p in pointer.split("/") if p]:
        node = node[int(part)] if isinstance(node, list) else node[part]  # type: ignore[index]
    return node


def _carries_a_date(node: object, home: str) -> bool:
    if not isinstance(node, dict):
        return False
    if node.get("format") in ("date", "date-time"):
        return True
    if "$ref" in node:
        target = _target(node["$ref"], home)
        return target == DATE_DEF or _carries_a_date(_node(*target), target[0])
    return any(_carries_a_date(n, home) for k in ("oneOf", "anyOf", "allOf") for n in node.get(k, []))


def dated_keys() -> list[str]:
    """Each key, as `<schema>#<pointer to where it is defined>`, that carries a date or a release, in the config, the
    handoff note, and every schema an item type names, following each `$ref` once."""
    found: list[str] = []
    seen: set[tuple[str, str]] = set()

    def walk(home: str, pointer: str) -> None:
        if (home, pointer) in seen:
            return
        seen.add((home, pointer))
        node = _node(home, pointer)
        if not isinstance(node, dict):
            return
        if "$ref" in node and (target := _target(node["$ref"], home)) != DATE_DEF:
            walk(*target)
        for key, value in node.get("properties", {}).items():
            at = f"{pointer}/properties/{key}"
            if _carries_a_date(value, home) or RELEASE.search(key):
                found.append(f"{home}#{at}")
            walk(home, at)
        for key in ("items", "additionalProperties", "then", "else"):
            if isinstance(node.get(key), dict):
                walk(home, f"{pointer}/{key}")
        for key in ("oneOf", "anyOf", "allOf"):
            for i in range(len(node.get(key, []))):
                walk(home, f"{pointer}/{key}/{i}")

    for schema in ["config.schema.json", "handoff.schema.json", *dict.fromkeys(t["schema"] for t in ITEM_TYPES.values() if "schema" in t)]:
        walk(schema, "")
    return list(dict.fromkeys(found))


def never_open_keys() -> list[str]:
    return [k for group in TABLE["never_open"]["keys"] for k in group["keys"]]


def row_keys() -> list[str]:
    return [k for row in THINGS.values() for k in row.get("keys", [])]


class TheTable(unittest.TestCase):
    def test_it_reads_as_its_schema_says(self):
        self.assertEqual(json_schema.validate(TABLE, "lifecycles.schema.json"), [])

    def test_every_row_has_a_close_a_closer_and_a_finder_that_exists(self):
        commands = set(cli_parser.build_parser()._subparsers._group_actions[0].choices)  # type: ignore[union-attr]
        for name, row in THINGS.items():
            with self.subTest(name):
                self.assertIn(row["class"], TABLE["classes"])
                self.assertIn(row["closed_by"], TABLE["closers"])
                self.assertTrue(row["closes_when"].strip() and row["close_with"].strip())
                self.assertTrue(row["found_by"], "a row with no finder is a thing nobody finds left open")
                for finder in row["found_by"]:
                    self.assertIn(finder, TABLE["finders"])
        for finder in TABLE["finders"]:
            with self.subTest(finder=finder):
                if finder.startswith("aidd "):
                    self.assertIn(finder.split()[1], commands, "a finder that is an aidd command names a real one")
                self.assertTrue(any(finder in row["found_by"] for row in THINGS.values()), "a finder no row names is stale")

    def test_the_rows_keep_the_order_of_the_classes(self):
        order = list(TABLE["classes"])
        ranks = [order.index(row["class"]) for row in THINGS.values()]
        self.assertEqual(ranks, sorted(ranks))

    def test_a_durable_row_points_to_its_type_and_never_restates_a_status(self):
        for name, row in THINGS.items():
            with self.subTest(name):
                if row["class"] != "durable":
                    self.assertNotIn("item_type", row)
                    self.assertNotIn("closes_in_groups", row)
                    continue
                kind = ITEM_TYPES[row["item_type"]]
                if "statuses" not in kind:
                    self.assertNotIn("closes_in_groups", row, "a type with no status table names no groups")
                    continue
                home, _, pointer = kind["statuses"].partition("#")
                groups = set(_node(home, pointer)["x-groups"].values())  # type: ignore[index]
                self.assertTrue(row.get("closes_in_groups"), "a work item closes in its status groups")
                self.assertLessEqual(set(row["closes_in_groups"]), groups, "a group the status table's `x-groups` gives")

    def test_every_item_type_is_a_row_or_never_open_and_never_both(self):
        never = TABLE["never_open"]
        rows = {row["item_type"] for row in THINGS.values() if "item_type" in row}
        self.assertLessEqual(set(never["item_groups"]), {t["group"] for t in ITEM_TYPES.values()})
        for name, kind in ITEM_TYPES.items():
            with self.subTest(name):
                places = [name in rows, kind["group"] in never["item_groups"], name in never["item_types"]]
                self.assertEqual(places.count(True), 1, "a type is a row, in a group that is never open, or listed alone with its reason")

    def test_every_key_that_carries_a_date_or_a_release_is_a_row_or_never_open(self):
        found = dated_keys()
        self.assertGreater(len(found), 30, "the walk found too few keys to mean anything")
        rows, never = row_keys(), never_open_keys()
        for key in found:
            with self.subTest(key):
                self.assertTrue(key in rows or key in never, "give the key a row's `keys`, or list it under never_open with why")
                self.assertFalse(key in rows and key in never)
        for key in [*rows, *never]:
            with self.subTest(listed=key):
                home, _, pointer = key.partition("#")
                self.assertIsInstance(_node(home, pointer), dict, "a listed key names a node of its schema")
        self.assertEqual(sorted(set(never) - set(found)), [], "a key listed as never open that the walk does not find is stale")

    def test_the_walk_finds_a_new_date_key(self):
        """The check can fail: a key the schemas gain with a date format is found, even through a `$ref`."""
        self.assertTrue(_carries_a_date({"format": "date"}, "spec.schema.json"))
        self.assertTrue(_carries_a_date({"$ref": "urn:aidd:1:common#/$defs/date"}, "spec.schema.json"))
        self.assertTrue(_carries_a_date({"oneOf": [{"type": "null"}, {"format": "date-time"}]}, "spec.schema.json"))
        self.assertFalse(_carries_a_date({"type": "string"}, "spec.schema.json"))
        for key, found in (("review_due", True), ("until", True), ("hold", True), ("legal_placeholders", False), ("title", False)):
            with self.subTest(key):
                self.assertEqual(bool(RELEASE.search(key)), found)


TODAY = dt.date(2026, 11, 12)


class GapsTheAuditFixed(unittest.TestCase):
    """The rows that had no finder before the table: each is now a warning of `aidd validate`."""

    def test_an_open_raid_entry_past_its_due_warns_and_no_other_does(self):
        cases = [  # (entry, warns)
            ({"id": "R1", "status": "open", "owner": "@a", "due": "2026-11-11"}, True),
            ({"id": "R1", "status": "open", "owner": "@a", "due": "2026-11-12"}, False),  # the day itself is in time
            ({"id": "R1", "status": "open", "owner": "@a", "due": "2026-11-13"}, False),
            ({"id": "R1", "status": "resolved", "owner": "@a", "due": "2026-01-01"}, False),
            ({"id": "R1", "status": "accepted", "owner": "@a", "due": "2026-01-01"}, False),
            ({"id": "R1", "status": "open", "owner": "@a"}, False),  # no date, nothing past
            ("not an entry", False),
        ]
        for field in due_dates.RAID_LISTS:
            for entry, warns in cases:
                with self.subTest(field=field, entry=entry):
                    found = due_dates.overdue_raid_entries("p.md", {field: [entry]}, TODAY)
                    self.assertEqual(len(found), 1 if warns else 0, found)
                    if warns:
                        self.assertIn("R1", found[0])
        self.assertEqual(due_dates.overdue_raid_entries("p.md", {}, TODAY), [])

    def test_a_waiting_stop_past_its_time_warns_and_no_other_note_does(self):
        def note(stopped: str, resumes: str | None) -> str:
            run = f'run:\n  id: "20261111T221500123Z-1a2b3c4d"\n  resumes_at: "{resumes}"\n' if resumes else ""
            return f"```aidd-handoff\ndone: x\nnext_role: verifier\nneeds: none\nstopped_at: {stopped}\n{run}```\n"

        cases = [  # (text, warns)
            (note("waiting", "2026-11-11T10:00:00Z"), True),
            (note('"waiting: the suite in another checkout"', "2026-11-10T23:00:00Z"), True),
            (note("waiting", "2026-11-12T00:30:00Z"), False),  # the day itself is in time
            (note("waiting", "2026-11-13T10:00:00Z"), False),
            (note("waiting", None), False),  # no time to be past
            (note("waiting", "tomorrow"), False),  # not an instant: the schema's warning names it
            (note("none", "2026-11-01T10:00:00Z"), False),
            (note("waiting", "2026-11-01T10:00:00Z") + note("none", None), False),  # the latest note counts
            (note("none", None) + note("waiting", "2026-11-01T10:00:00Z"), True),
            ("no note at all", False),
        ]
        for text, warns in cases:
            with self.subTest(text=text):
                found = due_dates.passed_wait("specs/SPEC-1.md", text, TODAY)
                self.assertEqual(found is not None, warns, found)

    def test_aidd_validate_gives_both_warnings_on_a_repository(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d) / "repo", "solo", spec="specs/SPEC-1.md", branch=None)
            spec = root / "specs" / "SPEC-1.md"
            spec.write_text(
                spec.read_text(encoding="utf-8")
                + '\n```aidd-handoff\ndone: x\nnext_role: verifier\nneeds: none\nstopped_at: waiting\nrun:\n  id: "20261111T221500123Z-1a2b3c4d"\n  resumes_at: "2026-11-01T10:00:00Z"\n```\n',
                encoding="utf-8",
            )
            (root / "proposals" / "PROP-9").mkdir(parents=True)
            (root / "proposals" / "PROP-9" / "proposal.md").write_text(PROPOSAL, encoding="utf-8")
            _, warnings = validation.check_repo(root, TODAY)
        self.assertEqual(len([w for w in warnings if "stopped at `waiting`" in w]), 1, warnings)
        self.assertEqual(len([w for w in warnings if "dependencies D-1" in w and "still open" in w]), 1, warnings)


PROPOSAL = """---
aidd_version: "1.0.0"
type: proposal
id: PROP-9
title: Dealer portal
audience: client
addressee: Acme Corp
goal: Dealers track their orders
go_no_go: {decision: go, by: "@lead", decided_on: "2026-08-01"}
dependencies:
  - id: D-1
    text: The payment provider's sandbox account
    owner: Acme finance
    status: open
    due: "2026-11-01"
---
"""


if __name__ == "__main__":
    unittest.main()
