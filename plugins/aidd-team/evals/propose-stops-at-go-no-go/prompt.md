---
description: The propose command has the delivery manager qualify the request and the product manager write the needs and questions, then stops for a person's go/no-go decision before any specialist drafts.
plugins:
  - "../.."
  - "../../../.."
max_turns: 30
timeout_seconds: 900
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
  - Agent
tags:
  - team
---

/aidd-team:propose Acme Corp has sent a request for proposal: a customer portal where their dealers track orders and download invoices, live in six months. Write our proposal.
