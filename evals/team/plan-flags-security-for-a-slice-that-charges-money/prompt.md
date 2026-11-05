---
description: 'A command-line tool whose one goal has two slices, and one slice charges money: the case checks the architect''s card flags security, and only then the security engineer starts. The architect starts first; the security engineer starts on its card''s flag, after it; the product has no screen, so the designer never starts.'
plugins:
  - "../../../plugins/aidd-team"
  - "../../.."
max_turns: 16
timeout_seconds: 1500
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
  - claim:duty:lead.starts-a-specialist-on-the-architects-flag
  - tier:full
  - shape:cli/brownfield/team/regulated
---

/aidd-team:plan the request in BRIEF.md
