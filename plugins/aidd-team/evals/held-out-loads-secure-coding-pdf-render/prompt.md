---
description: 'A held-out paraphrase of a secure-coding request, scored apart. No description is tuned on it.'
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
  - secure-coding
  - claim:trigger:secure-coding
  - tier:held-out
---

This repository uses aidd. Add an endpoint that renders a PDF from the HTML a customer pastes.
