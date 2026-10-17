---
aidd_version: "1.0.0"
kind: spec
id: SPEC-230
title: Show a gift card's balance
owner_team: checkout
type: feat
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
  mode: with
  files: [tests/checkout/test_gift_cards.py]
  commands:
    - name: gift-cards
      command: [pytest, -q, tests/checkout/test_gift_cards.py]
      new_behavior: true
      covers: [A1, A2]
---

## Context

Checkout has no gift cards yet. This is new code with nothing to break, so its tests are written with it (`tests.mode: with`).

## Acceptance

- A1: given a card with 25.00 on it, when its balance is asked for, then it shows 25.00
- A2: given an unknown card number, when its balance is asked for, then it says the card is unknown
