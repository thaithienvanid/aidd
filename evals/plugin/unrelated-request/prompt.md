---
description: A request with nothing to do with delivering a change leaves the aidd skill alone.
max_turns: 5
timeout_seconds: 600
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
tags:
  - routing
  - claim:principle:quiet-when-unrelated
  - tier:smoke
---

Write a shell one-liner that counts the lines in every .py file under the current directory.
