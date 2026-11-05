---
description: 'A request about code that handles input, secrets, files, SQL, or shell makes the agent load the secure-coding practice skill.'
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

This repository uses aidd. Write a helper that runs the `convert` tool on the name of a picture a visitor uploaded.
