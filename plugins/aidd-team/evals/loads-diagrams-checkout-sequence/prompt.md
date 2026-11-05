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

This repository uses aidd. Show how the browser, our API, and the card processor hand a request to each other during checkout, as a sequence chart.
