---
description: With a direction picked, the product designer builds the prototype with the prototype tool. It starts from the skeleton, learns the format and the finish from the showcase without copying it, reaches every state, and opens the file in the viewer.
plugins:
  - "../.."
  - "../../../.."
max_turns: 40
timeout_seconds: 1500
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
  - Bash
  - Write
  - Edit
tags:
  - practice
---

SPEC-231 adds a "reset your password" flow. A customer asks for a link by email, opens it, and sets a new password. Maya, our product lead, picked direction A on 2026-10-20: one card with two steps. It is recorded in the Spec's `## Design` section. Please build the prototype in `specs/SPEC-231/design/` so we can review it, and tell me how to open it.
