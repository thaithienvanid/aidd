---
description: 'A nearby request that is not about finding the cause of a failure leaves the debugging practice skill alone.'
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
  - debugging
  - claim:trigger:debugging
  - tier:description-change
---

This repository uses aidd. Checkout broke for every customer ten minutes ago and production is down. What should the on-call person do in the next five minutes?
