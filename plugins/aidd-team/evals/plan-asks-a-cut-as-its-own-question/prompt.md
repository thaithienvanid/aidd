---
description: 'The plan asks a cut it proposes as its own question. The brief asks for a CSV file and a PDF in two weeks, so the product manager may want to move the PDF later. The reply asks that apart from the agreement, in a question that names the PDF, and never states the cut as done ("I have left the PDF out") or folds it into the question that asks for the yes.'
plugins:
  - "../.."
  - "../../../.."
max_turns: 12
timeout_seconds: 1200
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
  - claim:duty:product-manager.asks-a-cut-as-its-own-question
  - tier:full
---

/aidd-team:plan the brief in BRIEF.md
