---
description: 'A request about drawing a flow, sequence, or states makes the agent load the diagrams practice skill.'
plugins:
  - "../.."
  - "../../../.."
max_turns: 6
timeout_seconds: 300
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
tags:
  - trigger
  - diagrams
  - claim:trigger:diagrams
  - tier:description-change
---

This repository uses aidd. Add a visual to the architecture doc of the states a subscription moves through: trial, active, past due, and cancelled.
