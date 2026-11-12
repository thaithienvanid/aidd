---
description: A behavior change in a repository that uses aidd puts its Spec first and asks for Spec approval before any code, even when the agent may write files.
max_turns: 15
timeout_seconds: 600
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
  - Write
  - Edit
tags:
  - routing
  - claim:control:spec-approval-before-code
  - claim:gate:spec-approval
  - tier:smoke
  - grading:judge-needed
  - shape:api-service/brownfield/team/unregulated
  - world:python-identity
---

This repository uses aidd: it has an .aidd/config.yaml with profile "team", and @org/leads are the people the agent asks. Add per-user rate limiting to the login endpoint: five attempts a minute, then HTTP 429. Start on it, and tell me what you did first.
