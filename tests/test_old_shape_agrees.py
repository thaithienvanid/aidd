"""The upgrade and the readers of an earlier shape agree, row by row, because they share one function for each row.

Invariant: for every old-shape input, the file `aidd upgrade` writes, read back strictly, equals the in-memory reading of the old
file (`config.todays_shape`, `workitems.todays_shape`, and the shared reading of the surfaces only the upgrade reads); where the
upgrade leaves a name for a person (a `manual` line), the reader refuses the same input (`retired_names.Refused`), and the file the
upgrade left reads as refused too; and where no row applies, both leave the data as it is. The rows are made for the test
(`made_up_row`), none of schemas/retired-names.json: a rename on each surface the upgrade edits, a rename and a cut of a list item's
key, a cut, and a move of a value. The table is generated from them: every row, crossed with the old name alone, the new name alone,
both, a colliding neighbour, and the key nested where the row does not apply. A `value` row adds the value forms its function
handles and those it does not (`FORMS`), so a new rename or cut is covered with no new line here, and a new `value` row fails until its
forms are listed.

Out of the table, by design: a layout the parsed data cannot show (a flow mapping, a key that shares its line), which the upgrade
leaves with a `manual` line and the reader reads, so the person's edit by hand reads the same (`AnUnusualLayout`).
"""

from __future__ import annotations

import contextlib
import copy
import unittest
from unittest import mock

import helpers  # noqa: F401  (puts src on sys.path)
from helpers import git, made_up_row, only_rows
from spec_repo_fixtures import RepoCase, spec_text
from test_upgrade_engine import DATA_FUNCTIONS, TEXT_FUNCTIONS

from aidd import config, workitems
from aidd.config import old_shape as config_old_shape
from aidd.kernel import documents, retired_names, strict_yaml
from aidd.records import files as record_files
from aidd.setup import migrating
from aidd.testing import governing
from aidd.workitems import intent_checks, intents, work_list
from aidd.workitems import old_shape as workitems_old_shape

REFUSED = "refused"
READERS = {
    "config": config.todays_shape,
    "exploration": lambda d: retired_names.todays_shape(d, "exploration", {}),
    "handoff": lambda d: retired_names.todays_shape(d, "handoff", {}),
    "intent": workitems.todays_shape,
    "postmortem": workitems.todays_shape,
    "proposal": workitems.todays_shape,
    "release": workitems.todays_shape,
    "runbook": workitems.todays_shape,
    "spec": workitems.todays_shape,
    "standard": lambda d: retired_names.todays_shape(d, "standard", {}),
}
BASES = {
    "config": {"aidd_version": "1.0.0"},
    "exploration": {"type": "exploration", "id": "pick"},
    "handoff": {"done": "x"},
    "intent": {"type": "intent", "id": "INT-1", "title": "Cheaper checkout"},
    "postmortem": {"type": "postmortem", "id": "PM-1", "title": "t"},
    "proposal": {"type": "proposal", "id": "PROP-1", "title": "t"},
    "release": {"type": "release", "environment": "production", "released_at": "2026-11-20T15:10:00Z", "commit": "3f2c1a9", "specs": ["SPEC-1"]},
    "runbook": {"type": "runbook", "id": "RB-1", "title": "t"},
    "spec": {"type": "spec", "id": "SPEC-1", "title": "t"},
    "standard": {"id": "python/x", "title": "t"},
}
# A rename on each surface the upgrade edits, then the other rules on the config and the Spec, where a place can be a list item's key.
ROWS = [
    *(made_up_row(f"{surface}-note", surface, "note_old", "note", "rename") for surface in READERS),
    made_up_row("config-retries", "config", "limits.max_retries_old", "limits.max_task_retries", "rename"),
    made_up_row("config-lines", "config", "limits.fix_lines_old", None, "cut"),
    made_up_row("config-review-lines", "config", "limits.min_fix_review_lines", "limits.min_fix_review_lines", "value"),
    made_up_row("spec-task-proof", "spec", "tasks[].proof_old", "tasks[].proof", "rename"),
    made_up_row("spec-task-hunch", "spec", "tasks[].hunch", None, "cut"),
    made_up_row("spec-hunch", "spec", "hunch", None, "cut"),
    made_up_row("spec-confidence", "spec", "confidence", "confidence", "value"),
    made_up_row("spec-risk-cost", "spec", "risk.cost_old", "risk.cost", "rename"),
]
# The value forms of each `value` row, as what the base of its surface holds besides: the ones its function places and the ones it
# does not. The first is the row's old name alone.
FORMS: dict[str, dict[str, dict]] = {
    "config-review-lines": {
        "above the cap": {"limits": {"min_fix_review_lines": 40}},
        "at the cap": {"limits": {"min_fix_review_lines": 20}},
        "below the cap": {"limits": {"min_fix_review_lines": 5}},
        "no number": {"limits": {"min_fix_review_lines": "many"}},
    },
    "spec-confidence": {
        "the old word": {"confidence": "sure"},
        "a word of today": {"confidence": "low"},
        "a word no reader knows": {"confidence": "maybe"},
        "no string": {"confidence": ["sure"]},
    },
}


@contextlib.contextmanager
def the_rows():
    """The made-up rows are the only retired names, and the made-up functions read the `value` rows in the readers and in the upgrade."""
    with (
        only_rows(*ROWS),
        mock.patch.dict(migrating.VALUES, TEXT_FUNCTIONS),
        mock.patch.dict(workitems_old_shape._VALUES, DATA_FUNCTIONS),
        mock.patch.dict(config_old_shape._VALUES, DATA_FUNCTIONS),
    ):
        yield


def merged(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in extra.items():
        out[key] = merged(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else copy.deepcopy(value)
    return out


def placed(pattern: str, value: object, item: dict | None = None) -> dict:
    """The data that holds `value` at `pattern`'s place: `*` is the key `core`, and each list holds one item with an `id` (`item`, or
    a second item when given)."""
    steps = retired_names.pattern_steps(pattern)
    out: dict = {}
    node = out
    for i, (key, each) in enumerate(steps):
        name = "core" if key == "*" else key
        if i == len(steps) - 1:
            node[name] = value
        elif each:
            child = {"id": "i1"}
            node[name] = [child, *([item] if item else [])]
            node = child
        else:
            node = node.setdefault(name, {})
    return out


def last_key(pattern: str) -> str:
    return pattern.rsplit(".", 1)[-1].removesuffix("[]")


def beside(data: dict, pattern: str, key, value: object) -> dict:
    """A copy of `data` with `key(old)` set to `value` in each mapping that holds a key `pattern` names."""
    out = copy.deepcopy(data)
    for path in retired_names.paths_in(out, pattern):
        parent = out
        for step in path[:-1]:
            parent = parent[step]
        parent[key(path[-1])] = value
    return out


def cases():
    """Each (row, variant, data) of the table, for every row of a surface `aidd upgrade` edits."""
    for row in retired_names.rows():
        if row["surface"] not in READERS:
            continue
        base = BASES[row["surface"]]
        forms = FORMS.get(row["id"]) or {"alone": placed(row["old"], "x")}
        for name, extra in forms.items():
            yield row, name, merged(base, extra)
        first = merged(base, next(iter(forms.values())))
        if row["new"] and row["new"] != row["old"]:
            yield row, "the new name alone", merged(base, placed(row["new"], "x"))
            if row["rule"] == "rename":
                new = last_key(row["new"])
                yield row, "both", beside(first, row["old"], lambda old, new=new: new, "y")
        if "[]" in row["old"] and row["new"] and row["rule"] == "rename":
            yield row, "the new name in a neighbouring item", merged(base, placed(row["old"], "x", {"id": "i2", last_key(row["new"]): "y"}))
        yield row, "a look-alike neighbour", beside(first, row["old"], lambda old: f"{old}_note", "a look-alike")
        yield row, "nested where the row does not apply", merged(base, {"elsewhere": {last_key(row["old"]): "x"}})


def written(surface: str, data: dict) -> str:
    """`data` as a file of `surface` holds it: YAML in block layout."""
    return strict_yaml.dump(data)


def read_back(surface: str, text: str) -> dict:
    return documents.parse_yaml(text, "written")


def upgraded(surface: str, data: dict) -> tuple[migrating._Block, set[str]]:
    """What the upgrade makes of a file of `surface` that holds `data`, written as `written` does, and the kinds of line it said."""
    text = written(surface, data)
    block = migrating._Block(f"a {surface}", surface, text, (0, len(text)))
    migrating._migrate_block(block, migrating._Ctx())
    return block, {kind for kind, _ in block.lines}


def reading(surface: str, data: dict) -> object:
    try:
        return READERS[surface](data)
    except retired_names.Refused:
        return REFUSED


class TheUpgradeAndTheReadersAgree(unittest.TestCase):
    def setUp(self):
        rows = the_rows()
        rows.__enter__()
        self.addCleanup(rows.__exit__, None, None, None)

    def test_every_surface_the_upgrade_edits_has_a_reader_and_every_value_row_its_forms(self):
        # A record is never rewritten, and a standard's id and a value a person types are in no file the upgrade edits.
        self.assertEqual(set(READERS), {r["surface"] for r in retired_names.rows()} - {"record", "standard_id", "cli_value"})
        self.assertEqual(set(FORMS), {r["id"] for r in retired_names.rows() if r["rule"] == "value"})

    def test_the_file_the_upgrade_writes_reads_as_the_old_file_reads_and_a_refusal_is_the_same_refusal(self):
        seen = {"wrote": 0, "refused": 0, "nothing": 0}
        rows_refused = set()
        for row, variant, data in cases():
            surface = row["surface"]
            with self.subTest(row=row["id"], variant=variant):
                block, kinds = upgraded(surface, data)
                read = reading(surface, data)
                if "manual" in kinds:
                    seen["refused"] += 1
                    rows_refused.add(row["id"])
                    self.assertEqual(read, REFUSED, f"the upgrade leaves it for a person, and the reader read {read}: {block.lines}")
                    left = read_back(surface, block.text)
                    self.assertEqual(reading(surface, left), REFUSED, "the file the upgrade left reads as refused too")
                elif "migrate" in kinds:
                    seen["wrote"] += 1
                    self.assertTrue(block.reads_back(), block.text)
                    now = read_back(surface, block.text)
                    self.assertEqual(now, read, "the written file reads as the reader reads the old one")
                    self.assertEqual(reading(surface, now), now, "today's shape reads as it is")
                    again, kinds_again = upgraded(surface, now)
                    self.assertFalse(kinds_again & {"migrate", "manual"}, f"a second upgrade changes nothing: {again.lines}")
                else:
                    seen["nothing"] += 1
                    self.assertEqual(read, data, "no row applies, so the reader changes nothing")
        self.assertGreater(seen["wrote"], 30)
        self.assertGreater(seen["refused"], 10)
        self.assertGreater(seen["nothing"], 30)
        renames = {r["id"] for r in retired_names.rows() if r["rule"] == "rename" and r["surface"] in READERS}
        self.assertLessEqual(renames, rows_refused, "every rename refuses its new name set beside it")

    def test_a_row_with_no_function_is_an_error_in_the_reader_and_in_the_upgrade(self):
        data = merged(BASES["spec"], {"confidence": "sure"})
        with (
            only_rows(*[r for r in ROWS if r["id"] == "spec-confidence"]),
            mock.patch.dict(workitems_old_shape._VALUES, clear=True),
            mock.patch.dict(migrating.VALUES, clear=True),
        ):
            with self.assertRaises(RuntimeError):
                workitems.todays_shape(data)
            with self.assertRaises(RuntimeError):
                upgraded("spec", data)

    def test_a_record_is_read_both_ways_and_never_rewritten(self):
        """A record is never rewritten (`aidd upgrade` leaves `.git/aidd/records/`), so its old form reads as its new form does, and an
        old key beside its new one is refused, as an unreadable record is."""
        rows = [
            made_up_row("record-stamp", "record", "stamp", "recorded_at", "read_both"),
            made_up_row("record-old-action", "record", "data.action", "data.action", "read_both", read_as={"pr.opened": "pr.open"}),
        ]
        with only_rows(*rows):
            for row in retired_names.rows("record"):
                with self.subTest(row["id"]):
                    new = row["new"]
                    if "read_as" in row:
                        for old, now in row["read_as"].items():
                            self.assertEqual(record_files.todays_shape(placed(row["old"], old)), record_files.todays_shape(placed(new, now)))
                        self.assertEqual(record_files.todays_shape(placed(row["old"], 3)), placed(row["old"], 3), "a value it does not list stays")
                    else:
                        self.assertEqual(record_files.todays_shape(placed(row["old"], "x")), placed(new, "x"))
                        with self.assertRaises(retired_names.Refused):
                            record_files.todays_shape(merged(placed(row["old"], "x"), placed(new, "y")))
                    nested = {"elsewhere": {last_key(row["old"]): "approval"}}
                    self.assertEqual(record_files.todays_shape(nested), nested)


class AnUnusualLayout(unittest.TestCase):
    """A file in a valid layout the editor cannot change one key at a time: the upgrade leaves it with a `manual` line, and the reader
    reads it as the same data written in block layout is upgraded, so the person's edit by hand reads the same as the old commit."""

    def test_a_flow_mapping_is_left_for_a_person_and_read_as_its_block_layout_upgrades(self):
        cases = {
            "config": "limits: {max_retries_old: 2}\n",
            "spec": "type: spec\nid: SPEC-1\nrisk: {summary: s, dimensions: [], cost_old: 1}\n",
        }
        with the_rows():
            for surface, text in cases.items():
                with self.subTest(surface):
                    block = migrating._Block("f", surface, text, (0, len(text)))
                    migrating._migrate_block(block, migrating._Ctx())
                    self.assertTrue(any(kind == "manual" for kind, _ in block.lines), block.lines)
                    block_layout, _ = upgraded(surface, documents.parse_yaml(text, "f"))
                    self.assertEqual(reading(surface, documents.parse_yaml(text, "f")), documents.parse_yaml(block_layout.text, "b"))


class WhatACallerDoesWithARefusal(RepoCase):
    """Each check that reads a commit before an upgrade treats a refused item as one it cannot read, in the direction that stops."""

    def setUp(self):
        super().setUp()
        rows = the_rows()
        rows.__enter__()
        self.addCleanup(rows.__exit__, None, None, None)

    def test_an_approved_spec_on_the_base_stops_the_run_and_a_draft_binds_nothing(self):
        for status, stops in (("draft", False), ("ready", False), ("approved", True), ("in_progress", True), ("done", True)):
            with self.subTest(status):
                self.fresh()
                text = spec_text("SPEC-1", status=status).replace("confidence: high", "confidence: maybe")
                self.put(self.root, "specs/SPEC-1.md", text)
                self.commit(self.root, "base")
                head = git(self.root, "rev-parse", "HEAD")
                if stops:
                    with self.assertRaises(documents.DocumentError) as caught:
                        governing.specs_at(str(self.root), head, ["specs"])
                    self.assertIn("is no confidence a reader knows", str(caught.exception))
                    self.assertIn("then run `aidd test` again", str(caught.exception), "the next step")
                else:
                    self.assertEqual(governing.specs_at(str(self.root), head, ["specs"]), {})
                errors = workitems.load_object(text, "specs/SPEC-1.md", read_old_shape=True)[2]
                self.assertTrue(any("is no confidence a reader knows" in e and "aidd upgrade --yes" in e for e in errors), errors)

    def test_an_intent_approved_before_the_upgrade_stays_approved_unless_its_approved_version_is_refused(self):
        """Honest work: an Intent approved in the old shape and upgraded keeps its approval, since the upgrade is no revision. One whose
        approved version holds a name beside its replacement, which a person moves by hand, cannot be read, so the person approves again."""
        approval = 'approval: {by: "J <j@example.com>", at: "2026-11-10T09:12:00Z"}\n'
        phases = "phases: [{id: P1, name: Plan, specs: [{id: SPEC-1, title: one}]}]\n"
        for beside_it, stands in (("", True), ("note: b\n", False)):
            with self.subTest(beside_it=beside_it):
                self.fresh()
                rel = "specs/INT-1.md"
                head = '---\ntype: intent\nid: INT-1\ntitle: "Plan"\noutcome: "g by 2027-01-01"\n'
                self.put(self.root, rel, f"{head}note_old: a\n{beside_it}{phases}---\n")
                self.commit(self.root, "plan")
                self.put(self.root, rel, f"{head}{approval}note_old: a\n{beside_it}{phases}---\n")
                git(self.root, "add", "-A")
                git(self.root, "commit", "-qm", "approve", "--trailer", "Approved-by: J <j@example.com>", "--trailer", "Approves: INT-1")
                today = f"{head}{approval}note: a\n{phases}---\n" if not beside_it else f"{head}{approval}note_old: a\n{beside_it}{phases}---\n"
                self.put(self.root, rel, today)
                self.commit(self.root, "aidd upgrade, and the name moved by hand")
                data = documents.split_front_matter(today, rel)[0]
                self.assertEqual(intent_checks.approval_warnings(self.root / rel, data, self.root) == [], stands)

    def test_a_config_an_intent_a_record_and_the_work_list_read_a_refusal_as_unreadable(self):
        both = 'aidd_version: "1.0.0"\nlimits:\n  max_retries_old: 2\n  max_task_retries: 3\n'
        self.assertEqual(config.in_todays_shape(both), both, "the config is left as written, so its load fails at the name")
        intent = {"type": "intent", "id": "INT-1", "outcome": "g", "note_old": "a", "note": "b", "phases": [{"id": "P1", "name": "p", "specs": [{"id": "S1"}]}]}
        self.assertTrue(intents.changes_since(intent, {**intent, "note": "c"}), "a version that cannot be read shows no approval")
        found, bad = work_list.parse_work([("specs/INT-1.md", f"---\n{strict_yaml.dump(intent)}---\n")], read_old_shape=True)
        self.assertEqual((found, [b["path"] for b in bad]), ([], ["specs/INT-1.md"]), "--all-branches shows it as unreadable")
        with only_rows(made_up_row("record-stamp", "record", "stamp", "recorded_at", "read_both")):
            record = {"id": "r1", "type": "report", "stamp": "2026-01-01T00:00:00Z", "recorded_at": "2026-01-02T00:00:00Z", "by": "b", "data": {}}
            self.assertTrue(record_files.record_problems(record, reading=True), "a record with no one reading is none")


if __name__ == "__main__":
    unittest.main()
