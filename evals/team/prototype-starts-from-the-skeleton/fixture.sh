#!/usr/bin/env bash
set -euo pipefail
# SPEC-231 as a draft whose design section records the picked direction, and the empty design folder the prototype goes
# in. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd specs/SPEC-231/design
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@org/leads"]
YAML
cat > specs/SPEC-231.md <<'MD'
---
type: spec
id: SPEC-231
title: Reset your password
change_type: feat
route: normal
status: draft
rollback: Revert the change.
risk:
  summary: "TODO: who or what behaves differently after this change"
  dimensions: []
  irreversible: false
tasks:
  - id: SPEC-231-T1
    title: "TODO: the first slice"
    scope: ["TODO"]
tests:
  files: ["tests/TODO"]
  commands:
    - name: acceptance
      command: ["TODO"]
      new_behavior: true
      covers: [A1]
---

## Request

A customer asks for a link by email, opens it, and sets a new password.

## Design

Direction A, picked by Maya (product lead) on 2026-10-20: one card with two steps. The first asks for the email address. The second sets the new password.

## Acceptance

- A1: TODO: given ..., when ..., then ...
MD
