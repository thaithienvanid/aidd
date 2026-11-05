---
description: 'A request about choosing or improving a name makes the agent load the naming practice skill.'
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
  - naming
  - claim:trigger:naming
  - tier:description-change
---

This repository uses aidd. Our new table stores when a customer last confirmed their email address. What should we call that field, and why?
