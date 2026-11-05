---
description: 'A nearby request that is not about drawing a flow, sequence, or states leaves the diagrams practice skill alone.'
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

This repository uses aidd. Our design doc and runbook are in Markdown. Give me one command that counts the headings in each file.
