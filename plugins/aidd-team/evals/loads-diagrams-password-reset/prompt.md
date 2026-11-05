---
description: 'A request about drawing a flow, sequence, or states makes the agent load the diagrams practice skill.'
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
  - diagrams
  - claim:trigger:diagrams
  - tier:description-change
---

This repository uses aidd. Sketch the steps of a password reset for a new teammate: the request, the email, the check of the link, and the new password.
