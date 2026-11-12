"""Every list of codes has one owner, and each copy of it either reads the owner or is pinned equal to it here. A copy that
drifts fails with the pair it belongs to named. This table holds the pairs of the codes a script matches: a step code, a stop
code, a reason code, a change type. A new copy of one of them is a new row, and a reader that reads the owner needs none."""

from __future__ import annotations

import unittest

import helpers  # puts src/ on the path and makes the run hermetic

from aidd import workitems
from aidd.delegation import policy
from aidd.kernel import resources
from aidd.views import work_item_detail, work_parts
from aidd.workitems import handoff_notes, step_reasons, steps, work_list

COMMON = resources.load_json("common.schema.json")["$defs"]


def template_change_types(name: str) -> list[str]:
    """The change types a Spec template's `change_type` line lists in its comment, for a person who fills it in by hand."""
    line = next(
        t for t in (helpers.ROOT / ".agents" / "skills" / "aidd" / "assets" / name).read_text(encoding="utf-8").splitlines() if t.startswith("change_type:")
    )
    return [word.strip() for word in line.partition("#")[2].split(",")]


class Owners(unittest.TestCase):
    def pairs(self) -> list[tuple[str, list, list]]:
        """(the pair, the copy, the owner), each as a list in the order it is kept in."""
        step = COMMON["step_code"]
        return [
            ("STEP_CODES keys, and the schema's step_code", list(workitems.STEP_CODES), step["enum"]),
            ("STEP_MEANINGS keys, and the schema's step_code", list(workitems.STEP_MEANINGS), step["enum"]),
            ("STEP_WORDS keys, and the schema's step_code", list(steps.STEP_WORDS), step["enum"]),
            ("x-who keys, and the schema's step_code", list(step["x-who"]), step["enum"]),
            ("x-meanings keys, and the schema's step_code", list(step["x-meanings"]), step["enum"]),
            ("the people who take a step, and next.who", sorted(set(step["x-who"].values())), sorted(COMMON["next"]["properties"]["who"]["enum"])),
            ("AGENT, PERSON, NOBODY, and next.who", sorted((steps.AGENT, steps.PERSON, steps.NOBODY)), sorted(COMMON["next"]["properties"]["who"]["enum"])),
            ("handoff_notes.stop_codes(), and the schema's stop_code", list(handoff_notes.stop_codes()), COMMON["stop_code"]["enum"]),
            (
                "the delegate check's reason_code, and the delegate group of findings.json",
                resources.load_json("delegate-check.schema.json")["$defs"]["reason_code"]["enum"],
                list(policy.reasons()),
            ),
            *(
                (f"the change types {name} lists in its comment, and the schema's change_type", template_change_types(name), COMMON["change_type"]["enum"])
                for name in ("spec.md", "spec-short.md")
            ),
        ]

    def test_each_copy_equals_its_owner(self):
        for name, copy, owner in self.pairs():
            with self.subTest(name):
                self.assertEqual(copy, owner)

    def test_a_next_step_code_is_the_step_code_list(self):
        self.assertEqual(COMMON["next"]["properties"]["code"]["$ref"], "#/$defs/step_code")

    def test_a_table_keyed_by_step_code_names_only_step_codes(self):
        """A subset needs no pair, but a code mistyped in one never matches and never fails."""
        subsets = {
            "step_reasons.SOURCES": step_reasons.SOURCES,
            "work_item_detail.HEADINGS": work_item_detail.HEADINGS,
            "work_item_detail.WAITS_FOR_BUILD": work_item_detail.WAITS_FOR_BUILD,
            "work_parts.NEEDS_ORDER": work_parts.NEEDS_ORDER,
            "work_parts.PLAIN_HEADING": work_parts.PLAIN_HEADING,
            "work_list._MOVE_ON": work_list._MOVE_ON,
        }
        for name, table in subsets.items():
            with self.subTest(name):
                self.assertLessEqual(set(table), set(COMMON["step_code"]["enum"]))


if __name__ == "__main__":
    unittest.main()
