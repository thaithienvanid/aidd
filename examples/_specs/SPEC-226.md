+++
aidd_version = "1.0.0"
kind = "spec"
id = "SPEC-226"
title = "Refund a partially shipped order"
owner_team = "checkout"
type = "feat"
route = "major"
confidence = "high"
open_questions = []
trace_id = "spec-226"
assisted_by = ["claude-code/claude-opus-5-5"]
rollback = "Revert the PR, redeploy, then confirm that a partial refund request returns 409 in staging."
residual_risk = "A refund issued before the rollback stays issued."

[risk]
summary = "Refunds move money: a wrong amount pays out too much or too little."
dimensions = ["financial"]
reversible = true

[[tasks]]
id = "TASK-226"
title = "Refund only the shipped lines"
scope = ["src/payments/refund.ts"]
assignee = "agent:claude-code"

[tests]
files = ["tests/payments/refund.test.ts"]

[[tests.commands]]
name = "refund"
command = ["npx", "vitest", "run", "tests/payments/refund.test.ts"]
new_behavior = true

[observe]
window = "24h"
signals = "refund amount per order against the shipped total, refund API error rate"
rollback_trigger = "Any refund above the shipped total"
+++

## Context

Refunds today cover the whole order. An order that shipped in part can only be refunded in full or not at all.

## Acceptance

| Order | Refund requested | Result |
| --- | --- | --- |
| 2 of 3 lines shipped | the 2 shipped lines | 200, those lines refunded |
| 2 of 3 lines shipped | all 3 lines | 409 |
