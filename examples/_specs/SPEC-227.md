---
aidd_version: "1.0.0"
kind: spec
id: SPEC-227
title: Show the order total in the buyer's currency
owner_team: checkout
type: feat
route: normal
confidence: high
open_questions: []
trace_id: spec-227
assisted_by: [claude-code/claude-opus-5-5]
rollback: Revert the PR; the web client shows the total in the store's currency again.
residual_risk: A total shown before the rollback keeps its converted amount.
risk:
  summary: The web client formats the order total with a new client library; no amount changes.
  dimensions: [third_party]
  reversible: true
tasks:
  - id: TASK-227
    title: Format the total with the new library
    scope: [web/package.json, lib/money.ts]
    assignee: agent:claude-code
tests:
  files: [tests/money.test.ts]
  commands:
    - name: money
      command: [npx, vitest, run, tests/money.test.ts]
      new_behavior: true
observe:
  window: "24h"
  signals: "checkout conversion, client errors on the order summary"
  rollback_trigger: "client errors on the order summary above 1% for 10 minutes"
---

## Context

The order summary in `lib/money.ts` shows the total in the store's currency. The code sits outside every folder the built-in rules name.

## Acceptance

```gherkin
Given a buyer whose currency differs from the store's
When the buyer opens the order summary
Then the total shows in the buyer's currency
```
