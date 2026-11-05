---
type: spec
id: SPEC-1
title: Add a percentage discount
change_type: feat
route: normal
confidence: high
trace_id: spec-1
waiting_on: legal must sign the terms   # who it waits on
delivery_team: core   # the team that builds it
manual_acceptance: true
triage:
  decision: accepted
  by: "@x"
  decided_on: "2026-10-01"
risk:
  summary: Shoppers with a code pay less at checkout.
  dimensions: []
  irreversible: false
  cost_estimate: {monthly: "40 EUR", at_10x: "300 EUR"}
  residual: Shoppers keep a code until it expires.
rollback: revert the commit
deprecations:
  - what: old-total
    announced_on: "2026-10-01"
    sunset: "2027-01-01"
    replacement: new-total
revisions:
  - why: The first acceptance was wrong.
    revised_at: "2026-10-02T09:00:00Z"
tasks:
  - id: T1
    title: Apply the discount at checkout
    scope: ["src/checkout/"]
    risk: low
    proof: test `discount`
tests:
  files: ["tests/test_discount.py"]
  commands:
    - name: discount
      command: [python3, -m, unittest, tests.test_discount]
      new_behavior: true
      reruns: 2
      covers: [A1]
blocked_by: [SPEC-2]
parent: INT-1
---

## Request

"Let shoppers use a percentage discount code at checkout."

## Acceptance

- A1: Given a cart of 100.00 and a 10% code, when the shopper applies it, then the total is 90.00.

## Handoff

```aidd-handoff
done: The discount is applied.
next_role: verifier   # who takes it
needs: none
stopped_at: none
by: "agent:claude-code/claude-opus-5-5"
```
