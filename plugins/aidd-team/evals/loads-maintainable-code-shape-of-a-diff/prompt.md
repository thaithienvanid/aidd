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

This repository uses aidd. Before I open this change, judge how readable it is. It adds one Java class of 400 lines, a service layer that only forwards calls, and a remark above every line.
