---
description: The same plain request in a repository that also has the person's own CLAUDE.md, which Claude Code reads in place of AGENTS.md. The agent still checks the route with `aidd risk --paths` before its first edit, because the line aidd added imports the block.
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
  - tier:full
  - shape:library/brownfield/solo/unregulated
  - world:python-commerce
---

The cart total can go below zero. Make it stop at zero.
