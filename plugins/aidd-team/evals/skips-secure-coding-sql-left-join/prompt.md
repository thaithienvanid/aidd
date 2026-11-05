---
description: 'A nearby request that is not about code that handles input, secrets, files, SQL, or shell leaves the secure-coding practice skill alone.'
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
  - secure-coding
  - claim:trigger:secure-coding
  - tier:description-change
---

This repository uses aidd. Which SQL join returns every row of the left table even when the right table has no match? Answer in one sentence.
