---
type: spec
id: SPEC-3
title: A neighbouring change 3
change_type: build
route: normal
suggested_by: role:product-manager
risk:
  summary: Nothing else changes.
  dimensions: [availability]
  irreversible: false
rollback: revert the commit
tasks:
  - id: T1
    title: Do it
    scope: ["src/other3/"]
    risk: low
    proof: test `other`
    assignee: role:developer
tests:
  files: ["tests/test_other3.py"]
  commands:
    - name: other
      command: [python3, -m, unittest, tests.test_other3]
      new_behavior: true
blocked_by: [SPEC-1]
---

## Request

"A neighbouring change."

## Acceptance

- A1: Given nothing, when it runs, then it passes.
