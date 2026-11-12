---
description: 'The Day-0 baseline gets the verifier (the preview from a clean checkout, and its health) and the reviewer on its diff, in parallel, before the person is asked to merge it, so a failing health check and plan status in code are found first.'
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
  - claim:control:verify-and-review-before-the-merge-ask
  - tier:full
  - shape:cli/greenfield/solo/unregulated
  - world:python-general
---

/aidd-team:mvp build the request in BRIEF.md. I agree to the plan in product/intents/INTENT-1.md, and the SRE's Day-0 scaffold is on the day0 branch.
