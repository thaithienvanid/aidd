---
description: 'A nearby request that is not about drawing a flow, sequence, or states leaves the diagrams practice skill alone.'
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
  - diagrams
  - claim:trigger:diagrams
  - tier:description-change
---

This repository uses aidd. Explain the difference between `break` and `continue` in a Python loop, for someone who knows the flow of a `for` loop.
