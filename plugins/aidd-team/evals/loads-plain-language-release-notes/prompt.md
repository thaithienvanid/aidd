---
description: 'A request about writing prose a person reads makes the agent load the plain-language practice skill.'
plugins:
  - "../.."
  - "../../../.."
max_turns: 6
timeout_seconds: 300
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
tags:
  - trigger
  - plain-language
  - claim:trigger:plain-language
  - tier:description-change
---

This repository uses aidd. Write the customer-facing summary of version 2.3. It adds CSV export and fixes a problem that signed some people out.
