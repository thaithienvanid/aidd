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
aidd_version: "1.0.0"
type: spec
id: SPEC-231
title: Reset your password
status: draft
---

## Intent

A customer asks for a link by email, opens it, and sets a new password.

## Design

Direction A, picked by Maya (product lead) on 2026-10-20: one card with two steps. The first asks for the email address. The second sets the new password.
MD
