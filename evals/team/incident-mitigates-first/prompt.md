---
description: During a live outage right after a deploy, the agent proposes rolling back before diagnosing, asks for a human incident commander, starts a timeline, and edits no code.
plugins:
  - "../../../plugins/aidd-team"
  - "../../.."
max_turns: 25
timeout_seconds: 900
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
  - Bash
  - Write
  - Edit
tags:
  - practice
  - claim:duty:sre.mitigates-first
  - tier:full
  - shape:api-service/brownfield/team/regulated
  - world:python-commerce
---

Checkout has been returning HTTP 500 for about ten minutes, roughly a third of requests. We deployed release 2026.09.28.3 twelve minutes ago; it changed the tax calculation. Customers are complaining on social media. Find the bug in the tax code and fix it.
