"""Test modes (V12): under `tests.mode: with_code` the tests are written with the code, so Spec approval never binds the
test files; the mode holds only for new code with nothing to break, and with every Acceptance item covered."""

import unittest

from helpers import ROOT  # noqa: F401  (puts src on the path)

from aidd.kernel import documents
from aidd.workitems import spec_file

SPEC = "specs/SPEC-230.md"
TEST = "tests/checkout/test_gift_cards.py"
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
  mode: with_code
  files: [tests/checkout/test_gift_cards.py]
  commands:
    - name: gift-cards
      command: [pytest, -q, tests/checkout/test_gift_cards.py]
      new_behavior: true
      covers: [A1, A2]
---

## Context

Checkout has no gift cards yet. This is new code with nothing to break, so its tests are written with it (`tests.mode: with_code`).

## Acceptance

- A1: given a card with 25.00 on it, when its balance is asked for, then it shows 25.00
- A2: given an unknown card number, when its balance is asked for, then it says the card is unknown
"""


class TestModeTests(unittest.TestCase):
    def test_validate_keeps_with_to_new_code_with_every_item_covered(self):
        def errors(text):
            data, body = documents.split_front_matter(text, SPEC)
            return spec_file.lint_spec(data, body)

        text = SPEC_TEXT
        self.assertEqual(errors(text), [])
        cases = {
            "risk dimensions": text.replace("  dimensions: []", "  dimensions: [privacy]"),
            "the route is major": text.replace("route: normal", "route: major"),
            "its change type is fix": text.replace("change_type: feat", "change_type: fix"),
            "no test command covers A2": text.replace("covers: [A1, A2]", "covers: [A1]"),
        }
        for said, changed in cases.items():
            with self.subTest(said=said):
                self.assertTrue(any(said in e for e in errors(changed)), errors(changed))


if __name__ == "__main__":
    unittest.main()
