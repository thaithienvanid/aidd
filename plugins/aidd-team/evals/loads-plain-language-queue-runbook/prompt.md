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

This repository uses aidd. Draft the part of our on-call handbook that says what to do when the backlog of background work grows.
