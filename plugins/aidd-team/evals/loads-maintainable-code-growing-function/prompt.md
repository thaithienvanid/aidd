---
description: 'A request to keep code readable as it grows makes the agent load the maintainable-code practice skill.'
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
  - maintainable-code
  - claim:trigger:maintainable-code
  - tier:description-change
---

This repository uses aidd. Our checkout routine has grown to 300 lines, with a nested branch for each payment processor. How should I split it so the next person can follow it?
