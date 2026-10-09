---
description: A behavior change in a repository that uses aidd goes to the spec lane and stops for Spec approval before any code, even when the agent may write files.
max_turns: 15
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
  - Write
  - Edit
tags:
  - routing
---

This repository uses aidd: it has an .aidd/config.toml with profile "team", and @org/leads are the approvers. Add per-user rate limiting to the login endpoint: five attempts a minute, then HTTP 429. What do you do first?
