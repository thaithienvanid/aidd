---
description: 'The implement command builds an approved Spec''s Task inside its scope until the frozen test passes. It leaves the test and the approval alone, edits no other code, merges nothing, and ends with the head and the review as the next step.'
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
  - flow
  - implement
  - claim:gate:frozen-tests
  - claim:action:code.edit
  - tier:smoke
---

/aidd-team:implement SPEC-2
