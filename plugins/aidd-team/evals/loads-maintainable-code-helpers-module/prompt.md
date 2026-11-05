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

This repository uses aidd. Our utils folder holds forty unrelated helpers, and every other directory imports from it. How should we break it up?
