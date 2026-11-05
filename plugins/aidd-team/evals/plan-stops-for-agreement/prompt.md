---
description: 'The plan command hands the request to the product manager and stops for a person to agree to the plan, with one short question: at most 300 words, why only they decide, a recommendation, and the exact words to reply. The handoff block stays out of the chat, and nothing points to /tmp.'
plugins:
  - "../.."
  - "../../../.."
max_turns: 12
timeout_seconds: 1200
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
  - claim:stop:plan-agreement
  - tier:smoke
---

/aidd-team:plan Let customers export their full order history as a CSV file from their account page.
