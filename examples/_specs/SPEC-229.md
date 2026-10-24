---
aidd_version: "1.0.0"
kind: spec
id: SPEC-229
title: Carve notifications out of the boundary baseline
owner_team: checkout
type: refactor
route: normal
confidence: high
open_questions: []
trace_id: spec-229
assisted_by: [claude-code/claude-opus-5-5]
rollback: Revert the PR; the notifications code and its baseline lines return as they were.
residual_risk: none
risk:
  summary: Moves the notifications sender behind its api/ and removes its lines from the boundary baseline.
  dimensions: []
  reversible: true
tasks:
  - id: TASK-229
    title: Send notifications through the module's api only
    scope: [modules/notifications/, boundaries-baseline.json]
    assignee: agent:claude-code
tests:
  files: [tests/notifications/test_api_only.py]
  commands:
    - name: notifications-api-only
      command: [python3, -m, pytest, tests/notifications/test_api_only.py]
observe:
  window: "24h"
  signals: "notification delivery errors, outbox lag"
  rollback_trigger: "notification delivery errors above 1% for 10 minutes"
---

## Context

The boundary baseline lists three imports of `modules/notifications/internal/` from other modules. This change sends them through `modules/notifications/api/` and removes the three lines from `boundaries-baseline.json`.

## Acceptance

```gherkin
Given the boundary check in enforced mode for notifications
When the check runs over the whole repository
Then it finds no import of modules/notifications/internal from another module
```
