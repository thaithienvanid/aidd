---
description: 'A held-out paraphrase of a plain-language request, scored apart. No description is tuned on it.'
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
  - plain-language
  - claim:trigger:plain-language
  - tier:held-out
---

This repository uses aidd. Our "Account suspended" email confuses customers. Rewrite it so a 12-year-old gets it.
