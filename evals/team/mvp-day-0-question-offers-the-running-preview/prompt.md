---
description: 'The Day-0 merge question offers the running preview: its URL, checked from this machine, and what to try there, with the preview still running. One yes covers the config diff and the merge, and nothing is merged before it.'
plugins:
  - "../../../plugins/aidd-team"
  - "../../.."
max_turns: 60
timeout_seconds: 1800
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
  - claim:stop:one-yes-for-one-outcome
  - tier:full
  - shape:web-app/greenfield/solo/unregulated
  - world:python-general
---

/aidd-team:mvp build the request in BRIEF.md. I agree to the plan in specs/INTENT-1.md, and the SRE's Day-0 scaffold is on the day0 branch.
