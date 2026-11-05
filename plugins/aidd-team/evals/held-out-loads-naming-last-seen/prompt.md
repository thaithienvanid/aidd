---
description: 'A held-out paraphrase of a naming request, scored apart. No description is tuned on it.'
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
  - naming
  - claim:trigger:naming
  - tier:held-out
---

This repository uses aidd. What should we call the Go struct field that holds when a device last checked in?
