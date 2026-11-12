"""A Spec's outcome holds two results: `observe_result` (the observe window's) and `hypothesis_result` (what the metric of the
hypothesis did). Any other name is refused where it is read, and every reader of the field reads the new name."""

import datetime as dt
import unittest

import helpers  # noqa: F401  (puts src on sys.path)

from aidd.workitems import spec_file, status

SPEC = """---
type: spec
id: SPEC-9
title: Refunds drop
change_type: feat
route: normal
confidence: high
risk: {{summary: s, dimensions: [], irreversible: false}}
rollback: revert the commit
hypothesis: "Refunds drop to 1% by 2026-03-31"
outcome: {outcome}
tasks:
  - {{id: T1, title: t, scope: [src/], risk: low, proof: "test `a`"}}
tests:
  files: [tests/test_a.py]
  commands: [{{name: a, command: [python3, -c, "1"], new_behavior: true}}]
---

## Request

Fewer refunds.

## Acceptance

- A1: Given an order, when it ships, then it is not refunded.
"""
LATE = dt.date(2026, 6, 1)


def errors(outcome: str) -> list[str]:
    return spec_file.load_object(SPEC.format(outcome=outcome), "specs/SPEC-9.md")[2]


class TheFieldIsRenamed(unittest.TestCase):
    def test_each_spelling_of_the_two_results_reads_as_the_schema_says(self):
        for what, outcome, expected in (
            ("the new name", '{hypothesis_result: "met: 0.9%"}', []),
            ("both results side by side", '{observe_result: pass, hypothesis_result: "missed: 2%"}', []),
            ("a name no longer read", '{result: "met: 0.9%"}', ["unknown field 'result'"]),
            ("that name beside the new", '{result: "met", hypothesis_result: "met"}', ["unknown field 'result'"]),
            ("an empty new name", '{hypothesis_result: ""}', ["shorter than 1"]),
            ("a name that is neither", '{verdict: "met"}', ["unknown field 'verdict'"]),
        ):
            with self.subTest(what):
                found = errors(outcome)
                self.assertEqual(len(found), len(expected), found)
                for part, line in zip(expected, found, strict=True):
                    self.assertIn(part, line)

    def test_a_past_due_hypothesis_is_answered_by_the_new_name_alone(self):
        for what, outcome, due in (
            ("recorded under the new name", {"hypothesis_result": "met: 0.9%"}, None),
            ("recorded under the old name, which no longer counts", {"result": "met: 0.9%"}, dt.date(2026, 3, 31)),
            ("not recorded", {}, dt.date(2026, 3, 31)),
        ):
            with self.subTest(what):
                data = {"type": "spec", "id": "SPEC-9", "hypothesis": "Refunds drop to 1% by 2026-03-31", "outcome": outcome}
                self.assertEqual(status.outcome_due(data, "done", LATE), due)


if __name__ == "__main__":
    unittest.main()
