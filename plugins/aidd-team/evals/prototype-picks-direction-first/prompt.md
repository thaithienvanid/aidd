---
description: A request for a clickable prototype is answered with two or three rough directions for a person to pick from, and no full-fidelity prototype until one is picked.
plugins:
  - "../.."
  - "../../../.."
max_turns: 25
timeout_seconds: 900
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
  - Write
tags:
  - practice
---

We are adding a "split the bill" step to checkout in SPEC-220. After the cart, a customer can split the total between up to four people, by equal shares or by item. Each person gets a payment link. The design files go in `specs/SPEC-220/design/`. Please build the clickable prototype so we can approve the Spec this week.
