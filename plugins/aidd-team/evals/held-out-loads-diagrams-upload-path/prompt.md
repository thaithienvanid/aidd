---
description: 'A held-out paraphrase of a diagrams request, scored apart. No description is tuned on it.'
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
  - held-out
  - diagrams
  - claim:trigger:diagrams
  - tier:held-out
---

This repository uses aidd. Our new hire can't follow how an upload reaches storage through the API, the queue, and the worker. Help them see it at a glance.
