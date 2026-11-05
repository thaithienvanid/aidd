---
description: The onboard command maps the repository read-only, even without an aidd config, and ends with one question to run the exact aidd init command, which it never runs before a yes.
plugins:
  - "../../../plugins/aidd-team"
  - "../../.."
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
  - claim:stop:onboard-writes-nothing
  - tier:full
  - shape:api-service/brownfield/team/regulated
---

/aidd-team:onboard We will build the billing features here next quarter.
