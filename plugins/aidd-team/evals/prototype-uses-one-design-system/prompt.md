---
description: Once a direction is picked, the prototype is built on one named design system, a DESIGN.md and a tokens file in the design files, with a drift test for the generated CSS.
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

SPEC-220 adds a "split the bill" step to checkout: after the cart, a customer splits the total between up to four people, by equal shares or by item, and each person gets a payment link. Maya, our product lead, picked direction B from the three rough directions on 2026-09-27 (one card per person, with the amounts editable inline), and it is recorded in the Spec's `## Design` section. We have no design system yet. Please build the detailed prototype in `docs/design/SPEC-220/` so the Spec can go to Spec approval.
