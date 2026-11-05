---
description: 'A held-out paraphrase of a maintainable-code request, scored apart. No description is tuned on it.'
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
  - maintainable-code
  - claim:trigger:maintainable-code
  - tier:held-out
---

This repository uses aidd. Reviewers keep missing bugs in `billing.ts`, because it's 1,200 lines. How should it be laid out?
