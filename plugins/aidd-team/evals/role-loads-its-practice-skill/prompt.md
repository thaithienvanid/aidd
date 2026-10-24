---
description: Inside a role, the developer subagent loads the practice skill for the Task's kind of work (debugging) with the Skill tool, since its agent file preloads only the aidd skill and secure coding, and reproduces the bug before it fixes it.
plugins:
  - "../.."
  - "../../../.."
max_turns: 30
timeout_seconds: 900
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
  - Agent
  - Bash
  - Write
  - Edit
tags:
  - practice
  - roles
---

Use the aidd-team:developer agent for this fast-lane fix. Our booking report says a stay from 2026-10-01 to 2026-10-03 lasts 2 nights, which is right. But since last week's change, the invoice line built by `nights_label` in `stays.py` prints "2 night" instead of "2 nights". The code is in `stays.py` in this workspace.
