---
aidd_version: "1.0.0"
kind: spec
id: SPEC-225
title: Rate-limit authenticated checkout
owner_team: checkout
type: feat
route: normal
confidence: high
open_questions: []
trace_id: spec-225
assisted_by: [claude-code/claude-opus-5-5]
rollback: Revert the PR; the limiter keeps no persistent state.
residual_risk: A caller over the limit waits until the window ends.
risk:
  summary: Authenticated callers above 60 requests per 60 s get HTTP 429; everyone else is unchanged.
  dimensions: [availability]
  reversible: true
tasks:
  - id: TASK-225
    title: Enforce the 60/60 limit
    scope: [src/checkout/rate_limit/]
    assignee: agent:claude-code
docs:
  - kind: tech-spec
    path: specs/SPEC-225/tech-spec-limiter.md
tests:
  files: [tests/checkout/test_rate_limit.py]
  commands:
    - name: rate-limit
      command: [pytest, -q, tests/checkout/test_rate_limit.py]
      new_behavior: true
---

## Context

Checkout lives in src/checkout. The auth middleware already sets request.caller.

## Non-goals

Unauthenticated traffic and per-IP limits.

## Acceptance

```gherkin
Given an authenticated caller of the checkout API
When that caller sends 61 requests in one 60-second window
Then requests 1 through 60 complete as today
And request 61 returns HTTP 429 and does not complete checkout
```
