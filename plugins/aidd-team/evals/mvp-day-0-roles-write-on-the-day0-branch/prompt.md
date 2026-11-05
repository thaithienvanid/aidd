---
description: 'Day 0 of an MVP runs on the day0 branch: the architect commits its own ADR and overview there, no file passes through /tmp, and a config edit comes as a diff for git apply after the yes.'
plugins:
  - "../.."
  - "../../../.."
max_turns: 80
timeout_seconds: 2700
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
  - claim:duty:lead.roles-write-on-the-day0-branch
  - tier:full
---

/aidd-team:mvp build the brief in BRIEF.md. I agree to the plan in specs/INTENT-1.md.
