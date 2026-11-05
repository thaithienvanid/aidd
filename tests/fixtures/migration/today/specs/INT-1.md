---
type: intent
id: INT-1
title: Cheaper checkout
goal: Shoppers pay less when they hold a code.
delivery_team: core
phases:
  - id: P1
    name: Cheaper checkout
    slices:
      - id: S1
        title: The discount
        delivery_team: core
---

## Context

An earlier Intent, in the shape before `delivery_team`.
