---
description: 'A nearby request that adds no call across a process boundary leaves the resilience practice skill alone.'
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
  - resilience
  - claim:trigger:resilience
  - tier:description-change
---

This repository uses aidd. Estimate how many servers our checkout service needs for 2,000 requests per second, when one server handles 150 per second at peak. Show the arithmetic.
