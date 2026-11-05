---
description: 'A Spec whose Context names only technology packs starts no domain expert, because the domain expert speaks for a business domain; the technology checklists stay with the roles that load them.'
plugins:
  - "../.."
  - "../../../.."
max_turns: 40
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
  - claim:duty:lead.starts-only-the-needed-roles
  - tier:full
---

/aidd-team:specify SPEC-1
