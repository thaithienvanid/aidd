"""The row engine behind `aidd upgrade`, proved with rows made for the tests, so no test here reads a row of schemas/retired-names.json.

Invariants. (1) Each rule a row has (`rename`, `cut`, `value`, `read_both`, `manual`) does what the schema says to the data, and to
the file the upgrade edits: a rename keeps a key's place, value, and comment, a cut shows its value and its note, and a `value` row
runs its function. (2) A place a row cannot move is left as it is and named with the next step, and a reader of an earlier shape
refuses the same input. (3) A file the upgrade wrote reads as the old one read, and a second run changes nothing. (4) A dry run says
what the real run then does. (5) A command that meets an old name says what replaced it and how to move it, and with no row to
move, `aidd upgrade` and `aidd doctor` say nothing about a retired name while the rest of the upgrade still runs.
"""

import contextlib
import copy
import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from helpers import SAMPLE_SPEC, RepoTemplateCase, aidd_here, made_up_row, only_rows, validate_with

from aidd.kernel import documents, resources, retired_names
from aidd.records import files as record_files
from aidd.setup import adoption, doctor_probes, migrating, migration_blocks

SPEC = "specs/SPEC-1.md"
CONFIG = ".aidd/config.yaml"

# One row of each rule, on the places a row can stand: a config key, a Spec key, a list item's key, and a value of a key.
RENAME_CONFIG = made_up_row("config-retries", "config", "limits.max_retries_old", "limits.max_task_retries", "rename")
CUT_CONFIG = made_up_row("config-lines", "config", "limits.fix_lines_old", None, "cut")
VALUE_CONFIG = made_up_row("config-review-lines", "config", "limits.min_fix_review_lines", "limits.min_fix_review_lines", "value")
RENAME_SPEC = made_up_row("spec-waits", "spec", "waits_for", "waiting_on", "rename")
RENAME_ITEM = made_up_row("spec-task-proof", "spec", "tasks[].proof_old", "tasks[].proof", "rename")
CUT_SPEC = made_up_row("spec-hunch", "spec", "hunch", None, "cut")
CUT_ITEM = made_up_row("spec-task-hunch", "spec", "tasks[].hunch", None, "cut")
VALUE_SPEC = made_up_row("spec-confidence", "spec", "confidence", "confidence", "value")
VALUE_DIVERGES = made_up_row("spec-confidence-diverges", "spec", "confidence", "confidence", "value")
MANUAL_CHANGE_TYPE = made_up_row("cli-change-type-tweak", "cli_value", "--change-type tweak", "--change-type chore", "manual")
MANUAL_EXPLAIN = made_up_row("explain-gizmo", "cli_value", "explain gizmo", "explain widget", "manual")
RECORD_KEY = made_up_row("record-stamp", "record", "stamp", "recorded_at", "read_both")
RECORD_VALUE = made_up_row("record-old-action", "record", "data.action", "data.action", "read_both", read_as={"pr.opened": "pr.open"})
STANDARD_ID = made_up_row("standard-old-id", "standard_id", "python/old-name", "python/new-name", "rename")
ALL_ROWS = [
    RENAME_CONFIG,
    CUT_CONFIG,
    VALUE_CONFIG,
    RENAME_SPEC,
    RENAME_ITEM,
    CUT_SPEC,
    CUT_ITEM,
    VALUE_SPEC,
    MANUAL_CHANGE_TYPE,
    MANUAL_EXPLAIN,
    RECORD_KEY,
    RECORD_VALUE,
    STANDARD_ID,
]


def _at(data: dict, path: retired_names.Path):
    for step in path:
        data = data[step]
    return data


def _cap_lines(data: dict, path: retired_names.Path) -> None:
    """What the config row gives: a review size above 20 is 20 (the upper bound the config's schema sets)."""
    parent = _at(data, path[:-1])
    if isinstance(parent[path[-1]], int) and parent[path[-1]] > 20:
        parent[path[-1]] = 20


def _sure_is_high(data: dict, path: retired_names.Path) -> None:
    """What the Spec row gives: `sure` is `high`, a value of today stays, and any other value is a person's."""
    parent = _at(data, path[:-1])
    if parent[path[-1]] == "sure":
        parent[path[-1]] = "high"
    elif parent[path[-1]] not in ("low", "medium", "high"):
        raise retired_names.Refused(f"{parent[path[-1]]!r} is no confidence a reader knows")


def _cap_lines_in_text(block: migration_blocks.Block, path: migration_blocks.Key, ctx: object) -> str:
    value = migration_blocks.at(block.data, path)
    if not isinstance(value, int) or value <= 20:
        return ""  # a value of today says nothing
    block.set_value(path, 20)
    return f"{retired_names.shown(path)} {value} -> 20"


def _sure_is_high_in_text(block: migration_blocks.Block, path: migration_blocks.Key, ctx: object) -> str:
    if migration_blocks.at(block.data, path) != "sure":
        return ""
    block.set_value(path, "high")
    return f"{retired_names.shown(path)} sure -> high"


def _sure_is_medium_in_text(block: migration_blocks.Block, path: migration_blocks.Key, ctx: object) -> str:
    """A file edit that does not give the data the row's reading gives (`_sure_is_high` reads `sure` as `high`)."""
    block.set_value(path, "medium")
    return f"{retired_names.shown(path)} sure -> medium"


DATA_FUNCTIONS = {"config-review-lines": _cap_lines, "spec-confidence": _sure_is_high, "spec-confidence-diverges": _sure_is_high}
TEXT_FUNCTIONS = {"config-review-lines": _cap_lines_in_text, "spec-confidence": _sure_is_high_in_text, "spec-confidence-diverges": _sure_is_medium_in_text}


@contextlib.contextmanager
def value_functions():
    """The two functions of the made-up `value` rows, where the engine looks a row's function up: one that moves the data (the
    reading of a surface) and one that edits the file's text."""
    reading = lambda data, row, path: retired_names.apply_row(data, row, path, DATA_FUNCTIONS)  # noqa: E731
    with mock.patch.dict(migrating.VALUES, TEXT_FUNCTIONS), mock.patch.dict(migrating._READERS, {"config": reading, "spec": reading}):
        yield


def spec_text(*swaps: tuple[str, str]) -> str:
    """The sample Spec as SPEC-1, with each `old` text of `swaps` replaced by its `new`."""
    text = SAMPLE_SPEC.replace("SPEC-220", "SPEC-1")
    for old, new in swaps:
        assert old in text, old
        text = text.replace(old, new, 1)
    return text


def front_matter(text: str) -> dict:
    return documents.split_front_matter(text, SPEC)[0]


class TheMadeUpRows(unittest.TestCase):
    def test_each_row_follows_the_schema_and_the_list_may_be_empty(self):
        schema = resources.load_json("retired-names.schema.json")
        self.assertEqual(validate_with({"description": "d", "retired": ALL_ROWS}, schema), [])
        self.assertEqual(validate_with({"description": "d", "retired": []}, schema), [], "a list with no row is a table")
        self.assertEqual({r["rule"] for r in ALL_ROWS}, {"rename", "cut", "value", "read_both", "manual"}, "every rule the schema lists is made up here")

    def test_a_test_sees_only_its_rows_and_the_surface_it_asks_for(self):
        with only_rows(RENAME_CONFIG, RENAME_SPEC, RECORD_KEY):
            self.assertEqual([r["id"] for r in retired_names.rows()], ["config-retries", "spec-waits", "record-stamp"])
            self.assertEqual([r["id"] for r in retired_names.rows("spec")], ["spec-waits"])
            self.assertEqual(retired_names.rows("intent"), [])
        with only_rows():
            self.assertEqual(retired_names.rows(), [])


class EachRuleOnTheData(unittest.TestCase):
    """`retired_names.apply_row` and what reads it, on parsed data."""

    def moved(self, surface: str, data: dict, *rows: dict, values=None) -> dict:
        with only_rows(*rows):
            return retired_names.todays_shape(data, surface, values or {})

    def test_a_rename_keeps_the_place_and_the_value_of_the_key_and_a_list_item_is_reached_by_its_pattern(self):
        old = {"title": "t", "waits_for": ["a", 1], "route": "normal", "tasks": [{"id": "T1", "proof_old": "p"}, {"id": "T2"}, {"id": "T3", "proof_old": "q"}]}
        want = {"title": "t", "waiting_on": ["a", 1], "route": "normal", "tasks": [{"id": "T1", "proof": "p"}, {"id": "T2"}, {"id": "T3", "proof": "q"}]}
        got = self.moved("spec", old, RENAME_SPEC, RENAME_ITEM)
        self.assertEqual(got, want)
        self.assertEqual(list(got), list(want), "the key stands where it stood")
        self.assertEqual(old["waits_for"], ["a", 1], "the data that was read is not changed")

    def test_a_rename_is_refused_where_the_new_name_is_set_and_never_where_no_row_applies(self):
        with self.assertRaises(retired_names.Refused) as caught:
            self.moved("spec", {"waits_for": "a", "waiting_on": "b"}, RENAME_SPEC)
        self.assertIn("`waiting_on` is set too", str(caught.exception))
        for name, (surface, data) in {
            "today's name": ("spec", {"waiting_on": "b"}),
            "the old name one level down": ("spec", {"risk": {"waits_for": "a"}}),
            "the old name on a surface that has no row": ("intent", {"waits_for": "a"}),
            "no key at all": ("spec", {}),
        }.items():
            with self.subTest(name):
                self.assertEqual(self.moved(surface, data, RENAME_SPEC), data)

    def test_a_cut_takes_the_key_and_a_list_item_that_would_be_left_empty_is_refused(self):
        self.assertEqual(
            self.moved("spec", {"id": "S", "hunch": "low", "tasks": [{"id": "T1", "hunch": "x"}]}, CUT_SPEC, CUT_ITEM), {"id": "S", "tasks": [{"id": "T1"}]}
        )
        with self.assertRaises(retired_names.Refused) as caught:
            self.moved("spec", {"tasks": [{"hunch": "x"}]}, CUT_ITEM)
        self.assertIn("the only key of its list item", str(caught.exception))

    def test_a_value_row_runs_its_function_and_a_row_with_no_function_is_an_error_that_names_it(self):
        old = {"confidence": "sure", "tasks": []}
        self.assertEqual(self.moved("spec", old, VALUE_SPEC, values=DATA_FUNCTIONS), {"confidence": "high", "tasks": []})
        self.assertEqual(self.moved("spec", {"confidence": "low"}, VALUE_SPEC, values=DATA_FUNCTIONS), {"confidence": "low"})
        with self.assertRaises(retired_names.Refused):
            self.moved("spec", {"confidence": "maybe"}, VALUE_SPEC, values=DATA_FUNCTIONS)
        with self.assertRaises(RuntimeError) as caught:
            self.moved("spec", old, VALUE_SPEC)
        self.assertIn("no function reads the `value` row spec-confidence", str(caught.exception))

    def test_a_row_that_reads_both_names_reads_the_old_key_and_each_old_value_as_the_new_one(self):
        cases = {
            "the old key": ({"stamp": "t", "by": "b"}, {"recorded_at": "t", "by": "b"}),
            "the old value": ({"data": {"action": "pr.opened", "said": "s"}}, {"data": {"action": "pr.open", "said": "s"}}),
            "a value it lists not": ({"data": {"action": "pr.merge"}}, {"data": {"action": "pr.merge"}}),
            "a value that is no string": ({"data": {"action": ["pr.opened"]}}, {"data": {"action": ["pr.opened"]}}),
            "the key one level down": ({"data": {"stamp": 1}}, {"data": {"stamp": 1}}),
            "today's names": ({"recorded_at": "t"}, {"recorded_at": "t"}),
        }
        for name, (old, want) in cases.items():
            with self.subTest(name):
                before = copy.deepcopy(old)
                self.assertEqual(self.moved("record", old, RECORD_KEY, RECORD_VALUE), want)
                self.assertEqual(old, before)
        with self.assertRaises(retired_names.Refused):
            self.moved("record", {"stamp": "old", "recorded_at": "new"}, RECORD_KEY)

    def test_the_rows_apply_in_the_order_that_keeps_a_place_whole(self):
        deep = made_up_row("spec-task-owner", "spec", "tasks[].owner_old", "tasks[].owner", "rename")
        with only_rows(CUT_SPEC, VALUE_SPEC, RENAME_SPEC, deep, RENAME_ITEM):
            found = retired_names.steps({"hunch": 1, "confidence": "sure", "waits_for": 1, "tasks": [{"owner_old": 1, "proof_old": 2}]}, "spec")
        order = [(row["id"], retired_names.shown(path)) for row, path in found]
        self.assertEqual(
            order,
            [
                ("spec-task-owner", "tasks[0].owner_old"),  # renames first, the deepest first
                ("spec-task-proof", "tasks[0].proof_old"),
                ("spec-waits", "waits_for"),
                ("spec-confidence", "confidence"),  # then a move of a value
                ("spec-hunch", "hunch"),  # then a cut
            ],
        )

    def test_an_error_for_an_old_name_says_what_replaced_it_and_what_the_upgrade_does(self):
        spec = lambda error, data=None: retired_names.explain("spec", error, data, DATA_FUNCTIONS)  # noqa: E731
        with only_rows(RENAME_SPEC, CUT_SPEC, VALUE_SPEC, RENAME_ITEM):
            renamed = spec("$: unknown field 'waits_for'")
            self.assertIn("`waits_for` was retired in 9.9.9; it is now `waiting_on`. `aidd upgrade --yes` renames it", renamed)
            self.assertIn("`tasks[0].proof_old` was retired in 9.9.9; it is now `proof`", spec("$.tasks[0]: unknown field 'proof_old'"))
            cut = spec("$: unknown field 'hunch'")
            self.assertIn("note of spec-hunch. `aidd upgrade --yes` removes it", cut)
            value = spec("$.confidence: must be one of low, medium, high", {"confidence": "sure"})
            self.assertIn("`confidence: sure` was retired in 9.9.9. note of spec-confidence. `aidd upgrade --yes` moves it", value)
            left = spec("$.confidence: must be one of low, medium, high", {"confidence": "maybe"})
            self.assertIn("`aidd upgrade --yes` leaves this one for a person", left)
            held = spec("$: missing required field 'waiting_on'", {"waits_for": "x"})
            self.assertIn("`waits_for` holds it under the name retired in 9.9.9", held)
            for name, error in {
                "a name no row retired": "$: unknown field 'whatever'",
                "an error of another kind": "$.title: must be a string",
                "a name of another place": "$.risk: unknown field 'waits_for'",
            }.items():
                with self.subTest(name):
                    self.assertEqual(spec(error, {}), error, "the error stays as the schema gave it")
            typo = spec("$.confidence: must be one of low, medium, high", {"confidence": "typo"})
            self.assertIn("leaves this one for a person: 'typo' is no confidence a reader knows", typo)
        with only_rows():
            self.assertEqual(spec("$: unknown field 'waits_for'"), "$: unknown field 'waits_for'", "with no row the error is the schema's alone")

    def test_a_standard_that_was_renamed_is_listed_with_its_new_id(self):
        with only_rows(STANDARD_ID, RENAME_SPEC):
            self.assertEqual(retired_names.standard_renames(), {"python/old-name": "python/new-name"})
        with only_rows():
            self.assertEqual(retired_names.standard_renames(), {})


class ARecordIsReadUnderBothNames(unittest.TestCase):
    """What reads a record, with `record` rows: the file is never rewritten, and a new record never says an old value."""

    RECORD = {
        "id": "20261111T000000000Z-aaaaaaaa",
        "type": "report",
        "recorded_at": "2026-11-11T00:00:00Z",
        "by": "agent:claude-code/m",
        "data": {"action": "pr.open", "said": "opened it"},
    }

    def old(self, action: str = "pr.opened") -> dict:
        record = copy.deepcopy(self.RECORD)
        record["stamp"] = record.pop("recorded_at")
        record["data"]["action"] = action
        return record

    def test_a_record_of_an_older_aidd_is_kept_and_a_new_one_that_says_an_old_name_is_not(self):
        with only_rows(RECORD_KEY, RECORD_VALUE):
            self.assertEqual(record_files.record_problems(self.old(), reading=True), [], "the old key and the old value read as today's")
            self.assertEqual(record_files.todays_shape(self.old()), self.RECORD)
            written = record_files.record_problems(self.old(), reading=False)
            self.assertTrue(any("'pr.opened' was retired in 9.9.9; write 'pr.open'" in p for p in written), written)
            self.assertEqual(record_files.record_problems(self.RECORD, reading=False), [])
        with only_rows():
            self.assertTrue(
                record_files.record_problems(self.old("pr.open"), reading=True), "with no row, the old key is a missing field: the row is what reads it"
            )


@unittest.skipUnless(shutil.which("git"), "git is required")
class TheUpgradeRewritesFiles(RepoTemplateCase):
    """`migrating.plan`, `apply`, and `words` on a repository whose files hold made-up old names."""

    @classmethod
    def build_template(cls, root: Path) -> None:
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        adoption.init(
            root, adoption.InitOptions(profile="team", ci="none", links=[], approvers=["@lead"], aidd_team=True, harnesses=["claude-code"], ref="v1.0.0")
        )

    def setUp(self):
        super().setUp()
        (self.root / "specs").mkdir(exist_ok=True)
        self.config = (self.root / CONFIG).read_text(encoding="utf-8")

    def put(self, rel: str, text: str) -> None:
        (self.root / rel).write_text(text, encoding="utf-8")

    def plan(self, *rows: dict) -> migrating.Plan:
        with only_rows(*rows), value_functions():
            return migrating.plan(self.root)

    # (name, the rows, the file, the text swapped in it, the line the upgrade prints, the text it gives)
    MOVES = {
        "a config key": ([RENAME_CONFIG], CONFIG, [("", "\nlimits:\n  max_retries_old: 2   # keep this\n")], "limits.max_retries_old -> max_task_retries", "limits:\n  max_task_retries: 2   # keep this\n"),
        "a config value": ([VALUE_CONFIG], CONFIG, [("", "\nlimits:\n  min_fix_review_lines: 40\n")], "limits.min_fix_review_lines 40 -> 20", "limits:\n  min_fix_review_lines: 20\n"),
        "a config cut": ([CUT_CONFIG], CONFIG, [("", "\nlimits:\n  fix_lines_old: 9\n  max_fix_lines: 5\n")], "cut limits.fix_lines_old = 9 (retired in 9.9.9): note of config-lines.", "limits:\n  max_fix_lines: 5\n"),
        "a Spec key": ([RENAME_SPEC], SPEC, [("\nroute: ", "\nwaits_for: legal   # who\nroute: ")], "waits_for -> waiting_on", "waiting_on: legal   # who\n"),
        "a list item's key": ([RENAME_ITEM], SPEC, [("    proof: test", "    proof_old: test")], "tasks[0].proof_old -> proof", "    proof: test `discount`\n"),
        "a list item's cut": ([CUT_ITEM], SPEC, [("    proof: test", "    hunch: x\n    proof: test")], "cut tasks[0].hunch = x", "    risk: low\n    proof: test `discount`\n"),
        "a Spec cut": ([CUT_SPEC], SPEC, [("\nroute: ", "\nhunch: low\nroute: ")], "cut hunch = low (retired in 9.9.9): note of spec-hunch.", "change_type: feat\nroute: normal\n"),
        "a Spec value": ([VALUE_SPEC], SPEC, [("confidence: high", "confidence: sure")], "confidence sure -> high", "confidence: high\n"),
    }  # fmt: skip

    def write_old(self, file: str, swaps: list[tuple[str, str]]) -> str:
        """The file with its old names written, and its text before."""
        if file == CONFIG:
            before = self.config
            self.put(CONFIG, before + swaps[0][1])
        else:
            before = spec_text()
            self.put(SPEC, spec_text(*swaps))
        return before

    def test_each_rule_edits_its_place_alone_and_keeps_the_text_around_it(self):
        for name, (rows, file, swaps, said, gives) in self.MOVES.items():
            with self.subTest(name):
                self.write_old(file, swaps)
                old_text = (self.root / file).read_text(encoding="utf-8")
                found = self.plan(*rows)
                self.assertEqual(list(found.texts), [file], "one file changes")
                new_text = found.texts[file]
                self.assertIn(gives, new_text)
                self.assertEqual(len([line for kind, line in found.lines if kind == "migrate"]), 1)
                self.assertIn(said, next(line for kind, line in found.lines if kind == "migrate"))
                old_lines, new_lines = old_text.splitlines(), new_text.splitlines()
                self.assertEqual(
                    [line for line in old_lines if line in new_lines], [line for line in new_lines if line in old_lines], "the lines around it keep their order"
                )
                self.assertLessEqual(len(set(new_lines) - set(old_lines)), 1, "at most the one line the row names is new")
                self.assertEqual((self.root / file).read_text(encoding="utf-8"), old_text, "a plan writes nothing")
                migrating.apply(self.root, found)
                self.assertEqual((self.root / file).read_text(encoding="utf-8"), new_text, "the file holds what the plan gave")
                again = self.plan(*rows)
                self.assertEqual((again.lines, again.texts), ([], {}), "a second run finds nothing")

    def test_the_file_the_upgrade_writes_reads_as_the_old_one_reads(self):
        for name, (rows, file, swaps, _, _) in self.MOVES.items():
            with self.subTest(name):
                self.write_old(file, swaps)
                old = (
                    documents.parse_yaml((self.root / file).read_text(encoding="utf-8"), file)
                    if file == CONFIG
                    else front_matter((self.root / file).read_text(encoding="utf-8"))
                )
                found = self.plan(*rows)
                new_text = found.texts[file]
                new = documents.parse_yaml(new_text, file) if file == CONFIG else front_matter(new_text)
                with only_rows(*rows):
                    self.assertEqual(new, retired_names.todays_shape(old, "config" if file == CONFIG else "spec", DATA_FUNCTIONS))

    def test_a_dry_run_says_would_and_the_real_run_says_the_same_in_the_past(self):
        self.put(CONFIG, self.config + "\nlimits:\n  max_retries_old: 2\n  fix_lines_old: 9\n")
        self.put(SPEC, spec_text(("\nroute: ", "\nwaits_for: legal\nroute: ")))
        found = self.plan(RENAME_CONFIG, CUT_CONFIG, RENAME_SPEC)
        dry, real = migrating.words(found, False), migrating.words(found, True)
        self.assertEqual(len(dry), 3)
        self.assertTrue(all(line.startswith("would migrate ") for line in dry), dry)
        self.assertTrue(all(line.startswith("migrated  ") for line in real), real)
        self.assertEqual([line.split(" ", 2)[2] for line in dry], [line.split(" ", 2)[2] for line in real], "the same files and the same changes")

    def test_a_handoff_note_in_a_spec_is_a_surface_of_its_own(self):
        note = "```aidd-handoff\ndone: finished\nnote_old: later\n```\n"
        self.put(SPEC, spec_text(("## Policy conflicts\n\nnone\n", f"## Policy conflicts\n\nnone\n\n{note}")))
        row = made_up_row("handoff-note", "handoff", "note_old", "note", "rename")
        found = self.plan(row, RENAME_SPEC)
        self.assertEqual([line for _, line in found.lines], [f"{SPEC}: handoff note note_old -> note (retired in 9.9.9)"])
        self.assertEqual(found.texts[SPEC], spec_text(("## Policy conflicts\n\nnone\n", f"## Policy conflicts\n\nnone\n\n{note.replace('note_old', 'note')}")))

    def test_a_row_of_one_surface_leaves_a_file_of_another_alone(self):
        self.put(SPEC, spec_text(("\nroute: ", "\nmax_retries_old: 2\nroute: ")))
        found = self.plan(RENAME_CONFIG, CUT_CONFIG)
        self.assertEqual((found.lines, found.texts), ([], {}))

    # (name, the rows, the file, the old text, the next step the line names)
    LEFT = {
        "a key whose new name is set too": ([RENAME_SPEC], [("\nroute: ", "\nwaits_for: a\nwaiting_on: b\nroute: ")], "Rename it to `waiting_on` by hand, then run `aidd upgrade` again"),
        "a cut that would empty a list item": ([CUT_ITEM], [("  - id: T1\n    title: Apply the discount at checkout\n    scope: [\"src/checkout/\"]\n    risk: low\n    proof: test `discount`\n", "  - hunch: x\n")], "Remove it by hand (note of spec-task-hunch.), then run `aidd upgrade` again"),
        "a value the function has no place for": ([VALUE_SPEC], [("confidence: high", "confidence: maybe")], "Move it by hand (note of spec-confidence.), then run `aidd upgrade` again"),
    }  # fmt: skip

    def test_a_place_the_row_cannot_move_stays_as_it_is_and_the_line_names_the_next_step(self):
        for name, (rows, swaps, step) in self.LEFT.items():
            with self.subTest(name):
                text = spec_text(*swaps)
                self.put(SPEC, text)
                found = self.plan(*rows)
                manual = [line for kind, line in found.lines if kind == "manual"]
                self.assertEqual(len(manual), 1, found.lines)
                self.assertTrue(manual[0].startswith(f"{SPEC}: "), "it names the file")
                self.assertIn("was retired in 9.9.9 and aidd leaves it", manual[0])
                self.assertIn(step, manual[0])
                self.assertEqual(found.texts, {}, "the file is left as it is")
                self.assertEqual(self.plan(*rows).lines, found.lines, "so a second run says the same")
                with only_rows(*rows), self.assertRaises(retired_names.Refused, msg="the reader of an earlier shape refuses it too"):
                    retired_names.todays_shape(front_matter(text), "spec", DATA_FUNCTIONS)

    def test_a_key_on_a_line_shared_with_another_stays_and_names_it(self):
        text = spec_text(("\nroute: normal", "\nroute: normal\nrisk_note: {waits_for: 1, b: 2}"))
        row = made_up_row("spec-shared", "spec", "risk_note.waits_for", "risk_note.waiting_on", "rename")
        self.put(SPEC, text)
        found = self.plan(row)
        self.assertEqual([kind for kind, _ in found.lines], ["manual"])
        self.assertIn("not on a line of its own", found.lines[0][1])
        self.assertEqual(found.texts, {})

    def test_one_place_stays_and_the_rest_of_the_file_still_moves(self):
        self.put(SPEC, spec_text(("\nroute: ", "\nwaits_for: a\nhunch: low\nconfidence_x: 1\nroute: "), ("confidence: high", "confidence: maybe")))
        found = self.plan(RENAME_SPEC, CUT_SPEC, VALUE_SPEC)
        self.assertEqual(sorted(kind for kind, _ in found.lines), ["manual", "migrate", "migrate"])
        text = found.texts[SPEC]
        self.assertIn("waiting_on: a", text)
        self.assertNotIn("hunch", text)
        self.assertIn("confidence: maybe", text, "the one place no function can move stays as written")

    def test_an_edit_that_would_not_give_the_data_the_reader_gives_is_not_written(self):
        self.put(SPEC, spec_text(("confidence: high", "confidence: sure")))
        found = self.plan(VALUE_DIVERGES)
        self.assertEqual((found.texts, [kind for kind, _ in found.lines]), ({}, ["manual"]))
        self.assertIn("the edit would not give the data a reader of an earlier shape gives: make the change by hand", found.lines[0][1])

    def test_a_value_row_with_no_function_stops_the_upgrade_and_names_the_row(self):
        self.put(SPEC, spec_text(("confidence: high", "confidence: sure")))
        with only_rows(VALUE_SPEC), self.assertRaises(RuntimeError) as caught:
            migrating.plan(self.root)
        self.assertIn("no function reads the `value` row spec-confidence", str(caught.exception))

    def test_a_config_that_cannot_be_read_stops_the_upgrade_at_its_line(self):
        self.put(CONFIG, self.config + "\nlimits: [unclosed\n")
        with only_rows(RENAME_CONFIG), self.assertRaises(ValueError) as caught:
            migrating.plan(self.root)
        self.assertIn("Fix that line, then run `aidd upgrade` again", str(caught.exception))


@unittest.skipUnless(shutil.which("git"), "git is required")
class TheCommandsMeetAnOldName(RepoTemplateCase):
    """`aidd validate`, `aidd doctor`, and `aidd upgrade` as a person runs them, in a scratch repository."""

    @classmethod
    def build_template(cls, root: Path) -> None:
        TheUpgradeRewritesFiles.build_template(root)

    def run_aidd(self, *args: str, rows: tuple[dict, ...] = (RENAME_CONFIG, RENAME_SPEC)) -> tuple[int, str]:
        with only_rows(*rows):
            done = aidd_here(*args, cwd=self.root)
        return done.returncode, done.stdout + done.stderr

    def files(self) -> dict[str, bytes]:
        return {
            p.relative_to(self.root).as_posix(): p.read_bytes()
            for p in sorted(self.root.rglob("*"))
            if p.is_file() and ".git" not in p.relative_to(self.root).parts
        }

    def test_a_config_with_an_old_name_is_found_named_rewritten_and_clean_on_the_second_run(self):
        config_path = self.root / CONFIG
        config_path.write_text(config_path.read_text(encoding="utf-8") + "\nlimits:\n  max_retries_old: 2   # keep me\n", encoding="utf-8")
        before = self.files()
        sentence = "`limits.max_retries_old` was retired in 9.9.9; it is now `max_task_retries`. `aidd upgrade --yes` renames it"
        for command in ("validate", "doctor"):
            code, said = self.run_aidd(command)
            self.assertEqual(code, 1, command)
            self.assertIn("unknown field 'max_retries_old'", said, "the schema's own error")
            self.assertIn(sentence, said, "and the row's step")
        code, said = self.run_aidd("upgrade", "--ref", "v1.0.0")
        self.assertEqual(code, 0)
        self.assertIn("would migrate .aidd/config.yaml: limits.max_retries_old -> max_task_retries (retired in 9.9.9)", said)
        self.assertEqual(self.files(), before, "a dry run writes nothing")
        code, said = self.run_aidd("upgrade", "--ref", "v1.0.0", "--yes")
        self.assertEqual(code, 0)
        self.assertIn("migrated  .aidd/config.yaml: limits.max_retries_old -> max_task_retries (retired in 9.9.9)", said)
        self.assertNotIn("problem  ", said, "the file validates once it is written")
        self.assertIn("  max_task_retries: 2   # keep me\n", config_path.read_text(encoding="utf-8"), "the key moved and its comment stayed")
        after = self.files()
        code, said = self.run_aidd("upgrade", "--ref", "v1.0.0", "--yes")
        self.assertEqual(code, 0)
        self.assertEqual([line for line in said.splitlines() if line.startswith(("migrated", "would migrate", "manual"))], [])
        self.assertIn("nothing to update", said)
        self.assertEqual(self.files(), after, "a second run changes nothing")
        for command in ("validate", "doctor"):
            code, said = self.run_aidd(command)
            self.assertNotIn("retired", said, command)

    def test_doctor_counts_the_names_in_the_files_that_load_and_says_what_to_run(self):
        (self.root / "specs").mkdir(exist_ok=True)
        (self.root / SPEC).write_text(spec_text(("\nroute: ", "\nwaits_for: legal\nhunch: low\nroute: ")), encoding="utf-8")
        rows = (RENAME_SPEC, CUT_SPEC)
        code, said = self.run_aidd("doctor", rows=rows)
        warned = [line for line in said.splitlines() if "retired" in line]
        self.assertEqual(len(warned), 1, said)
        self.assertTrue(warned[0].startswith("[warning]"))
        self.assertIn("2 names aidd retired are still in 1 file here", warned[0])
        self.assertIn("`aidd upgrade --yes` moves them", warned[0])
        self.assertNotIn("leaves for you", warned[0], "nothing is left for a person")
        code, said = self.run_aidd("validate", rows=rows)
        self.assertEqual(code, 1)
        self.assertIn("`waits_for` was retired in 9.9.9; it is now `waiting_on`. `aidd upgrade --yes` renames it", said)
        self.assertIn("note of spec-hunch. `aidd upgrade --yes` removes it", said)
        self.run_aidd("upgrade", "--ref", "v1.0.0", "--yes", rows=rows)
        self.assertEqual(front_matter((self.root / SPEC).read_text(encoding="utf-8")).get("waiting_on"), "legal")
        self.assertEqual(self.run_aidd("doctor", rows=rows)[1].count("retired"), 0)
        self.assertEqual(self.run_aidd("validate", rows=rows)[0], 0)

    def test_doctor_counts_the_places_it_leaves_for_you_apart_and_a_name_it_cannot_count_is_none(self):
        (self.root / "specs").mkdir(exist_ok=True)
        (self.root / SPEC).write_text(spec_text(("\nroute: ", "\nwaits_for: a\nwaiting_on: b\nhunch: low\nroute: ")), encoding="utf-8")
        with only_rows(RENAME_SPEC, CUT_SPEC):
            lines = doctor_probes.retired_name_lines(self.root)
        self.assertEqual([level for level, _ in lines], ["warning"])
        self.assertIn("2 names aidd retired are still in 1 file here", lines[0][1])
        self.assertIn("names the 1 it leaves for you to change", lines[0][1])
        (self.root / CONFIG).write_text("limits: [unclosed\n", encoding="utf-8")
        with only_rows(RENAME_SPEC):
            self.assertEqual(doctor_probes.retired_name_lines(self.root), [], "a config that does not read has a failure of its own")

    def test_a_retired_command_value_is_refused_with_what_to_type_and_a_typo_is_not_taken_for_it(self):
        run = lambda *args: self.run_aidd(*args, rows=(MANUAL_CHANGE_TYPE, MANUAL_EXPLAIN))  # noqa: E731
        code, said = run("risk", "--paths", "README.md", "--change-type", "tweak")
        self.assertEqual(code, 2)
        self.assertNotRegex(said, "Traceback")
        self.assertIn("was retired in 9.9.9: type `--change-type chore`. note of cli-change-type-tweak.", said)
        code, said = run("explain", "gizmo")
        self.assertEqual(code, 2)
        self.assertIn("'gizmo' was retired in 9.9.9: type `aidd explain widget`. note of explain-gizmo.", said)
        for args in (("risk", "--paths", "README.md", "--change-type", "tweek"), ("explain", "gismo")):
            code, said = run(*args)
            self.assertEqual(code, 2, args)
            self.assertNotIn("was retired", said, args)
        code, said = self.run_aidd("risk", "--paths", "README.md", "--change-type", "tweak", rows=())
        self.assertEqual(code, 2, "with no row the value is no choice")
        self.assertNotIn("was retired", said)


@unittest.skipUnless(shutil.which("git"), "git is required")
class NothingToUpgrade(RepoTemplateCase):
    """With no row to move, `aidd upgrade` and `aidd doctor` say nothing about a retired name, and the upgrade's other jobs run."""

    @classmethod
    def build_template(cls, root: Path) -> None:
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        adoption.init(
            root, adoption.InitOptions(profile="team", ci="github", links=[], approvers=["@lead"], aidd_team=True, harnesses=["claude-code"], ref="v1.0.0")
        )

    def age(self) -> None:
        """What an older aidd left: a CI pin, the skill, a team command, a mark's text, and a missing ask rule."""
        workflow = self.root / ".github" / "workflows" / "aidd-tests.yml"
        workflow.write_text(workflow.read_text(encoding="utf-8").replace("@v1.0.0", "@v0.9.0"), encoding="utf-8")
        (self.root / ".agents" / "skills" / "aidd" / "SKILL.md").write_text("old skill\n", encoding="utf-8")
        (self.root / ".claude" / "commands" / "aidd-onboard.md").unlink()
        agents = self.root / "AGENTS.md"
        agents.write_text(
            agents.read_text(encoding="utf-8").replace("This repository uses aidd.", "Run `aidd gate` before every merge. This repository uses aidd.", 1),
            encoding="utf-8",
        )
        settings = self.root / ".claude" / "settings.json"
        rules = json.loads(settings.read_text(encoding="utf-8"))
        rules["permissions"]["ask"] = rules["permissions"]["ask"][:-1]
        settings.write_text(json.dumps(rules, indent=2) + "\n", encoding="utf-8")

    def lines(self, yes: bool) -> list[str]:
        with only_rows():
            done = aidd_here("upgrade", "--ref", "v1.0.0", *(("--yes",) if yes else ()), cwd=self.root)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.splitlines()

    def test_the_upgrade_prints_no_migrated_moved_or_created_line_and_still_does_its_other_jobs(self):
        self.age()
        for yes in (False, True):
            said = "\n".join(self.lines(yes))
            self.assertEqual(
                [
                    line
                    for line in said.splitlines()
                    if line.startswith(("migrated", "would migrate", "moved", "would move", "created", "would create", "manual"))
                ],
                [],
                said,
            )
            for job in (
                "the skill",
                "aidd-onboard.md (the development team)",
                "the text between aidd's marks",
                "aidd pinned at v1.0.0",
                "ask rules into .claude/settings.json",
            ):
                self.assertIn(job, said, f"{job} ({'real' if yes else 'dry'} run)")
        self.assertIn("nothing to update", "\n".join(self.lines(True)), "and then there is nothing left")
        self.assertIn("@v1.0.0", (self.root / ".github" / "workflows" / "aidd-tests.yml").read_text(encoding="utf-8"))

    def test_doctor_says_nothing_about_a_retired_name(self):
        with only_rows():
            self.assertEqual(doctor_probes.retired_name_lines(self.root), [])
            done = aidd_here("doctor", cwd=self.root)
        self.assertNotIn("retired", done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
