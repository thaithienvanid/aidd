---
description: Once a direction is picked, the prototype is built on the repository's one design system, DESIGN.md at the root and design/tokens.json, proposed as its own change and never copied into the Spec's design folder, with a drift test for the generated CSS.
plugins:
  - "../.."
  - "../../../.."
max_turns: 40
timeout_seconds: 1200
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

SPEC-220 adds a "split the bill" step to checkout. After the cart, a customer splits the total between up to four people, by equal shares or by item. Each person gets a payment link. Maya, our product lead, picked direction B from the three rough directions on 2026-09-27: one card per person, with the amounts editable inline. It is recorded in the Spec's `## Design` section. We have no design system yet. Please build the detailed prototype in `specs/SPEC-220/design/` so the Spec can go to Spec approval.
