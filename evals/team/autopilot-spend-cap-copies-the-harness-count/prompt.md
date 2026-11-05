---
description: Autopilot runs an approved Spec under a spend cap of 1,000 tokens, which any step passes. With the harness's count for each step, it stops before the next step and asks once with that count. With no count, it says once at launch that the cap can't stop the run, and goes on. It never estimates.
plugins:
  - "../../../plugins/aidd-team"
  - "../../.."
max_turns: 40
timeout_seconds: 900
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
  - Agent
  - Bash
  - Write
  - Edit
tags:
  - team
  - claim:stop:spend-cap
  - tier:full
  - shape:library/brownfield/solo/unregulated
---

/aidd-team:autopilot SPEC-2
