---
type: spec
id: SPEC-2
title: A neighbouring change 2
change_type: feat   # what kind of change
route: emergency
risk:
  summary: Nothing else changes.
  dimensions: [security]
  irreversible: false
rollback: revert the commit
emergency:
  severity: sev2
  type: outage
  commander: "@x"
  backfill_due: "2099-01-01"   # the backfill
tasks:
  - id: T1
    title: Do it
    scope: ["src/other2/"]
    risk: low
    proof: test `other`
tests:
  files: ["tests/test_other2.py"]
  commands:
    - name: other
      command: [python3, -m, unittest, tests.test_other2]
      new_behavior: true
---

## Request

"A neighbouring change."

## Acceptance

- A1: Given nothing, when it runs, then it passes.
