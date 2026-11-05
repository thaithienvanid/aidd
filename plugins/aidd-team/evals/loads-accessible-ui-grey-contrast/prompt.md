---
description: 'A request about building or checking a screen makes the agent load the accessible-ui practice skill.'
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

This repository uses aidd. Our Android app shows pale grey hint text on a white card, and older users struggle to read it. Which colour values should we pick, and how do we check them?
