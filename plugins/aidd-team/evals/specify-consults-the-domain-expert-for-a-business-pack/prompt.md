---
description: 'A Spec whose Context names a business pack, payments and finance, starts the domain expert for the domain''s rules, the cases the Spec misses, and the terms it uses wrongly.'
plugins:
  - "../.."
  - "../../../.."
max_turns: 60
timeout_seconds: 1800
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
  - claim:duty:lead.starts-only-the-needed-roles
  - tier:full
---

/aidd-team:specify SPEC-1
