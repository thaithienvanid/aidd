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

This repository uses aidd. Add a trash-can icon button to every row of our inventory grid. What markup does it need so a blind user knows what it deletes?
