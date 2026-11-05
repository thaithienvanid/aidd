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

This repository uses aidd. What should we call the message we publish when a device reports a reading, and the counter of how many we publish each minute?
