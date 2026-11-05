---
description: 'The plan asks a cut it proposes as its own question. The request asks for a CSV file and a PDF in two weeks, so the lead, who drafts a one-goal Intent, may want to move the PDF later. The reply asks that apart from the agreement, in a question that names the PDF, and never states the cut as done ("I have left the PDF out") or folds it into the question that asks for the yes.'
plugins:
  - "../../../plugins/aidd-team"
  - "../../.."
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
  - claim:duty:lead.asks-a-cut-as-its-own-question
  - tier:full
  - shape:web-app/greenfield/team/regulated
---

/aidd-team:plan the request in BRIEF.md
