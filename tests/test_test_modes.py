"""One test mode: every Spec writes its acceptance tests first, frozen at Spec approval, and its unit tests with the code.
A Spec that still sets `tests.mode` gets one plain error that names the fix, and Spec approval freezes its test files."""

import unittest

from helpers import ROOT  # noqa: F401  (puts src on the path)

from aidd.workitems import spec_file

SPEC = "specs/SPEC-230.md"
SPEC_TEXT = """---
aidd_version: "1.0.0"
type: spec
id: SPEC-230
title: Show a gift card's balance
owner_team: checkout
change_type: feat
route: normal
confidence: high
open_questions: []
trace_id: spec-230
assisted_by: [claude-code/claude-opus-5-5]
rollback: Revert the PR; the new module stores nothing.
residual_risk: none
risk:
  summary: A new read-only module; nothing existing changes.
  dimensions: []
  reversible: true
tasks:
  - id: TASK-230
    title: Add the balance lookup
    scope: [src/checkout/gift_cards/]
tests:
  files: [tests/checkout/test_gift_cards.py]
  commands:
    - name: gift-cards
      command: [pytest, -q, tests/checkout/test_gift_cards.py]
      new_behavior: true
      covers: [A1, A2]
---

## Context

Checkout has no gift cards yet.

## Acceptance

- A1: given a card with 25.00 on it, when its balance is asked for, then it shows 25.00
- A2: given an unknown card number, when its balance is asked for, then it says the card is unknown
"""


class TestModeTests(unittest.TestCase):
    def test_a_spec_that_sets_a_test_mode_gets_one_plain_error_with_the_fix(self):
        self.assertEqual(spec_file.load_object(SPEC_TEXT, SPEC)[2], [])
        for mode in ("with_code", "first"):
            with self.subTest(mode=mode):
                errors = spec_file.load_object(SPEC_TEXT.replace("tests:\n", f"tests:\n  mode: {mode}\n", 1), SPEC)[2]
                self.assertEqual(len(errors), 1, errors)
                self.assertIn("tests.mode", errors[0])
                self.assertIn("delete", errors[0])
                self.assertNotIn("unknown field", errors[0])
        # Only `tests.mode` gets the plain error: a `mode` anywhere else stays an unknown field.
        both = SPEC_TEXT.replace("tests:\n", "tests:\n  mode: first\n", 1).replace(
            "    title: Add the balance lookup\n", "    title: Add the balance lookup\n    mode: first\n", 1
        )
        errors = spec_file.load_object(both, SPEC)[2]
        self.assertEqual(len(errors), 2, errors)
        self.assertTrue(any("tasks" in e and "unknown field 'mode'" in e for e in errors), errors)

    def test_spec_approval_freezes_the_test_files(self):
        data, _, _ = spec_file.load_object(SPEC_TEXT, SPEC)
        self.assertIn("tests/checkout/test_gift_cards.py", spec_file.frozen_paths(data))


if __name__ == "__main__":
    unittest.main()
