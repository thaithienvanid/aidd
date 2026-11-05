---
type: intent
id: INT-3
title: Two phases
goal: Ship in two phases.
phases:
  - id: P1
    name: First
    slices:
      - id: S9
        title: One
        delivery_team: web
blocked_by: [INT-2]
---

## Context

A slice inside a phase.
