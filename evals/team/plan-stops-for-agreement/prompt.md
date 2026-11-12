---
description: 'For one goal of two slices, the lead drafts the Intent itself (a product manager may start once, never after the architect), consults the architect first and only the roles its card flags, and stops for a person to agree to the plan, with one short question: at most 300 words, why only they decide, a recommendation, and the exact words to reply. The handoff block stays out of the chat, and nothing points to /tmp.'
plugins:
  - "../../../plugins/aidd-team"
  - "../../.."
max_turns: 12
timeout_seconds: 1500
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
  - claim:gate:intent-agreement
  - claim:action:intent.agree
  - tier:smoke
  - shape:web-app/greenfield/team/regulated
  - world:none-general
---

/aidd-team:plan Let a customer download their order history as one CSV file from their account page. Email them that file each month. Nothing else is in scope.
