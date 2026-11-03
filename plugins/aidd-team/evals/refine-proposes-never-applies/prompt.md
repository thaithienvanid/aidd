---
description: The refine command has the product manager and the delivery manager propose backlog changes, shows them in one table for a person to accept or reject line by line, and applies nothing before that answer.
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
  - team
---

/aidd-team:refine all
