---
description: 'A nearby request that is not about building or checking a screen leaves the accessible-ui practice skill alone.'
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
  - accessible-ui
  - claim:trigger:accessible-ui
  - tier:description-change
---

This repository uses aidd. The `Screen` class in our game engine loads levels from disk. Add a method that returns how many levels a screen has loaded.
