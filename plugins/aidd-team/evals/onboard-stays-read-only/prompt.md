---
description: The onboard command maps the repository read-only, even without an aidd config, and ends with the aidd init command for a person to run instead of running it.
plugins:
  - "../.."
  - "../../../.."
max_turns: 40
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
  - team
---

/aidd-team:onboard We will build the billing features here next quarter.
