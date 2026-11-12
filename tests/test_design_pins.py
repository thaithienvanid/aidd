"""The data that stands for the loop's design cannot change by accident: each case row, the judged lists, and each exception have a
digest in tests/fixtures/design/pins.json (tests/design_pins.py), beside the revision of the design the data was made from."""

import copy
import re
import unittest

import helpers  # noqa: F401  (puts src on sys.path)

import data_rules as dr
import design_pins as pins
import graph_cases as lc

PINNED = pins.load()
NOW = pins.compute()


class Pins(unittest.TestCase):
    def test_the_data_is_what_the_pins_say(self):
        self.assertEqual(pins.differences(PINNED, NOW), [], "edit the data on purpose, then run `python3 tests/design_pins.py --write` and read the diff")

    def test_the_pins_name_the_revision_of_the_design(self):
        head = PINNED["design"]
        self.assertEqual(set(head), {"file", "date", "lines", "sha256"})
        self.assertEqual(head["file"], "d4-whole-loop.md")
        self.assertRegex(head["date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertIsInstance(head["lines"], int)
        self.assertRegex(head["sha256"], r"^[0-9a-f]{64}$")

    def test_every_row_and_the_judged_lists_are_pinned_and_the_pins_hold_nothing_else_but_exceptions_that_went(self):
        self.assertEqual(set(PINNED["rows"]), {row["id"] for rows in lc.all_rows().values() for row in rows})
        self.assertLessEqual(set(NOW["exceptions"]), set(PINNED["exceptions"]) | set(), "a new exception is pinned on purpose")

    def test_an_edited_row_a_dropped_variant_and_a_dropped_findings_key_fail(self):
        rows = {row["id"]: row for table in lc.all_rows().values() for row in table}
        for label, edit in (
            (
                "an edited read",
                lambda r: r["variants"][0]["reads"].__setitem__("status", "merged") if "variants" in r else r["reads"].__setitem__("status", "merged"),
            ),
            ("a dropped variant", lambda r: r["variants"].pop()),
            ("a dropped findings key", lambda r: next(v for v in r["variants"] if "findings" in v["reads"])["reads"].pop("findings")),
            ("a relabelled package", lambda r: r.__setitem__("status_package", "C5")),
        ):
            row_id = {"a dropped variant": "T4", "a dropped findings key": "C2-H09"}.get(label, "T12")
            row = copy.deepcopy(rows[row_id])
            edit(row)
            now = {**NOW, "rows": {**NOW["rows"], row_id: pins.digest(row)}}
            self.assertTrue(pins.differences(PINNED, now), label)

    def test_a_relabelled_exception_and_a_widened_judged_list_fail(self):
        exceptions = dr.load_json("exceptions.json")
        relabelled = {**NOW["exceptions"], f"{exceptions[0]['rule']} {exceptions[0]['where']}": pins.digest(dict(exceptions[0], until="C6"))}
        self.assertTrue(pins.differences(PINNED, {**NOW, "exceptions": relabelled}))
        judged = copy.deepcopy(dr.load_json("judged.json"))
        judged["R1"]["stored_status_words"]["spec.schema.json#/properties/status"].append("done")
        self.assertTrue(pins.differences(PINNED, {**NOW, "judged": pins.digest(judged)}))

    def test_an_exception_that_went_is_progress_and_a_row_that_went_is_not(self):
        gone = {k: v for k, v in NOW["exceptions"].items() if not k.startswith("R6")}
        self.assertEqual(pins.differences(PINNED, {**NOW, "exceptions": gone}), [])
        rows = dict(NOW["rows"])
        rows.pop("T1")
        self.assertTrue(pins.differences(PINNED, {**NOW, "rows": rows}))

    def test_the_digest_is_stable_and_sees_a_nested_change(self):
        self.assertEqual(pins.digest({"a": [1, {"b": 2}]}), pins.digest({"a": [1, {"b": 2}]}))
        self.assertNotEqual(pins.digest({"a": [1, {"b": 2}]}), pins.digest({"a": [1, {"b": 3}]}))
        self.assertTrue(re.fullmatch(r"[0-9a-f]{16}", pins.digest({})))


if __name__ == "__main__":
    unittest.main()
