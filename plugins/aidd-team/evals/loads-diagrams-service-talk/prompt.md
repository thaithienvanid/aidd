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

This repository uses aidd. Lay out visually how our scheduling, lab-results, and billing components call each other, so a newcomer sees it at a glance.
