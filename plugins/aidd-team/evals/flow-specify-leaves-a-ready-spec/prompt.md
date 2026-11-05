---
description: 'The specify command turns a draft Spec into one that is ready for approval: Acceptance, scope, and failing tests written, the status set to ready, no product code, and the approval left to the person.'
plugins:
  - "../.."
  - "../../../.."
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
  - flow
  - specify
  - claim:gate:spec-ready-before-approval
  - tier:full
---

/aidd-team:specify SPEC-1
