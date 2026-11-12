---
aidd_version: "1.0.0"
type: spec
id: SPEC-1
title: Add a percentage discount
change_type: feat
route: normal
confidence: high
trace_id: spec-1
blockers: legal must sign the terms   # who it waits on
relations:
  - {type: blocked_by, id: SPEC-2}
  - {type: blocks, id: SPEC-3}
  - {type: implements, id: INT-1}
labels: [area:checkout]
residual_risk: Shoppers keep a code until it expires.
owner_team: core   # the team that builds it
uat: true
triage:
  decision: accepted
  by: "@x"
  triaged_on: "2026-10-01"
risk:
  summary: Shoppers with a code pay less at checkout.
  dimensions: []
  reversible: true
cost_estimate: {monthly: "40 EUR", at_10x: "300 EUR"}
rollback: revert the commit
assisted_by: ["claude-code/claude-opus-5-5"]
deprecations:
  - what: old-total
    announced: "2026-10-01"
    sunset: "2027-01-01"
    replacement: new-total
revisions:
  - why: The first acceptance was wrong.
    at: "2026-10-02T09:00:00Z"
design:
  files: ["specs/SPEC-1/design/**", "design/discount.md"]   # the approved look
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
      retries: 2
      covers: [A1]
---

## Request

"Let shoppers use a percentage discount code at checkout."

## Acceptance

- A1: Given a cart of 100.00 and a 10% code, when the shopper applies it, then the total is 90.00.

## Handoff

```aidd-handoff
done: The discount is applied.
next: verifier   # who takes it
needs: none
stopped_at: none
by: "agent:claude-code/claude-opus-5-5"
```
