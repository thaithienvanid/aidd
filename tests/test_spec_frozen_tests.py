"""Every Spec writes its acceptance tests first, frozen at Spec approval, and its unit tests with the code. Spec approval
freezes the Spec's test files."""

import unittest

from helpers import ROOT  # noqa: F401  (puts src on the path)

from aidd.workitems import spec_file

SPEC = "specs/SPEC-230.md"
SPEC_TEXT = """---
type: spec
id: SPEC-230
title: Show a gift card's balance
change_type: feat
route: normal
confidence: high
open_questions: []
trace_id: spec-230
rollback: Revert the PR; the new module stores nothing.
risk:
  summary: A new read-only module; nothing existing changes.
  dimensions: []
  irreversible: false
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


class FrozenTestsTests(unittest.TestCase):
    def test_spec_approval_freezes_the_test_files(self):
        data, _, errors = spec_file.load_object(SPEC_TEXT, SPEC)
        self.assertEqual(errors, [])
        self.assertIn("tests/checkout/test_gift_cards.py", spec_file.frozen_paths(data))


if __name__ == "__main__":
    unittest.main()
