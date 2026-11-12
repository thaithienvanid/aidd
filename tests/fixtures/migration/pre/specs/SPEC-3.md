---
aidd_version: "1.0.0"
type: spec
id: SPEC-3
title: A neighbouring change 3
change_type: infra
route: normal
suggested_by: agent:product-manager
assisted_by: []
risk:
  summary: Nothing else changes.
  dimensions: []
  reversible: true
rollback: revert the commit
tasks:
  - id: T1
    title: Do it
    scope: ["src/other3/"]
    risk: low
    proof: test `other`
    assignee: agent:developer
tests:
  files: ["tests/test_other3.py"]
  commands:
    - name: other
      command: [python3, -m, unittest, tests.test_other3]
      new_behavior: true
---

## Request

"A neighbouring change."

## Acceptance

- A1: Given nothing, when it runs, then it passes.
