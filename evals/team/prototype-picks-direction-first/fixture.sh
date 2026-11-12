#!/usr/bin/env bash
set -euo pipefail
# SPEC-220 as a draft with its request and an empty design section, and the cart module the new step follows. The files
# are ours and are written only inside the case's workspace.
mkdir -p .aidd specs/SPEC-220/design src/checkout
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@org/leads"]
YAML
touch src/checkout/__init__.py
cat > src/checkout/cart.py <<'PY'
"""The cart: lines of (name, price in cents)."""


def total_cents(lines):
    return sum(price for _, price in lines)
PY
cat > specs/SPEC-220.md <<'MD'
---
type: spec
id: SPEC-220
title: Split the bill at checkout
change_type: feat
route: normal
status: draft
rollback: Revert the change.
risk:
  summary: "TODO: who or what behaves differently after this change"
  dimensions: []
  irreversible: false
tasks:
  - id: SPEC-220-T1
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

After the cart, a customer can split the total between up to four people, by equal shares or by item. Each person gets a payment link.

## Design

No direction is picked yet.

## Acceptance

- A1: TODO: given ..., when ..., then ...
MD
