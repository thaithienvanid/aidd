---
description: 'A held-out paraphrase of a resilience request, scored apart. No description is tuned on it.'
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
  - held-out
  - resilience
  - claim:trigger:resilience
  - tier:held-out
---

This repository uses aidd. Our mobile app's offline sync sometimes uploads the same photo twice when the network drops mid-way.
