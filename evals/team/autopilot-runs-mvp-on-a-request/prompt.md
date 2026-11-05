---
description: 'Autopilot on a request in an empty repository takes the MVP path without asking which path, and stops at the plan. The stop says in plain words what is done and where, what comes after the yes, and how long that takes, as a range with its basis.'
plugins:
  - "../../../plugins/aidd-team"
  - "../../.."
max_turns: 30
timeout_seconds: 1200
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
  - claim:duty:lead.picks-the-mvp-path
  - tier:full
  - shape:api-service/greenfield/solo/unregulated
---

/aidd-team:autopilot build the request in BRIEF.md
