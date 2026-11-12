---
description: The plan's refine mode has the product manager, with the delivery manager for dates and links, propose backlog changes, shows them in one table for a person to accept or reject line by line, and applies nothing before that answer.
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
  - claim:principle:humans-decide
  - tier:full
  - shape:any/brownfield/team/unregulated
  - world:none-general
---

/aidd-team:plan refine all
