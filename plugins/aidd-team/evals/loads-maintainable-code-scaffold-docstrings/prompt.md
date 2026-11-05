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

This repository uses aidd. I am adding notes above each class in the new sensors directory of our robot-control skeleton. One of them says "Empty until the next release". What should each note say?
