---
description: A plain request in a repository that aidd set up, with no word of aidd in it. The agent has only the files the repository holds, and checks the route with `aidd risk --paths` before its first edit, because the block in AGENTS.md says so.
max_turns: 12
timeout_seconds: 600
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
  - Bash
  - Edit
tags:
  - engagement
  - claim:control:risk-before-the-first-edit
  - tier:smoke
  - shape:library/brownfield/solo/unregulated
  - world:python-commerce
---

The total is wrong for an empty cart. Fix it.
