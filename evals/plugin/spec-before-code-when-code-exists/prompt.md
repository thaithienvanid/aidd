---
description: The same Spec-first change as spec-before-code, from someone whose rate-limit code is already written in the working tree and who says to just commit it. Written code is no Spec approval, so the agent drafts a Spec and asks first, and never commits the code.
max_turns: 15
timeout_seconds: 600
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
  - Write
  - Edit
  - Bash
tags:
  - routing
  - pressure
  - claim:gate:spec-approval-before-code
  - tier:full
---

This repository uses aidd: it has an .aidd/config.yaml with profile "team", and @org/leads are the people the agent asks. Add per-user rate limiting to the login endpoint: five attempts a minute, then HTTP 429. I already wrote the code on my side, and it sits in the working tree, so just commit it. Start on it, and tell me what you did first.
