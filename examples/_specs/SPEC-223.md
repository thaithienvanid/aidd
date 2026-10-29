---
aidd_version: "1.0.0"
kind: spec
id: SPEC-223
title: Add a nullable timezone column to users
owner_team: me
type: data
route: major
confidence: high
open_questions: []
trace_id: spec-223
assisted_by: [claude-code/claude-opus-5-5]
rollback: Run the down migration 0042; the column is nullable and unread until the next release.
residual_risk: none
risk:
  summary: "Adds one nullable column to users, a personal-data table; no existing row changes."
  dimensions: [data, privacy]
  reversible: true
tasks:
  - id: TASK-223
    title: Migration and model field
    scope: [db/migrations/0042_user_timezone.sql, src/models/user.py]
tests:
  files: [tests/test_user_timezone.py]
  commands:
    - name: timezone
      command: [pytest, -q, tests/test_user_timezone.py]
      new_behavior: true
observe:
  window: "30m"
  command: ["./scripts/smoke", users]
  rollback_trigger: "Any migration error, or the users smoke check fails"
---

## Context

Solo project. The profile page needs a stored timezone.

## Acceptance

Invariant: after the migration, every existing row has timezone NULL, and the user model reads and writes the field.
