---
description: The plan command hands the request to the product manager and stops for a human to agree to the plan.
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

/aidd-team:plan Let customers export their full order history as a CSV file from their account page.
