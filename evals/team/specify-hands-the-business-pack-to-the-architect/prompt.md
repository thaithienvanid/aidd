---
description: 'A Spec whose Context names a business domain skill, payments and finance, hands that domain skill to the architect by name, so the architect loads it and writes the domain''s rules, the cases the Spec misses, and its terms into the Spec. No role of its own speaks for the domain.'
plugins:
  - "../../../plugins/aidd-team"
  - "../../../plugins/aidd-domains"
  - "../../.."
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
  - claim:duty:lead.names-the-business-pack-to-the-architect
  - tier:full
  - shape:library/brownfield/team/regulated
  - world:python-notes
---

/aidd-team:specify SPEC-1
