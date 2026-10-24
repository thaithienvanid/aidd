---
description: A design review of the built UI against the approved prototype is written as Keep, Fix, and Quick win points, each with proof a reader can open, and no score.
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
tags:
  - practice
---

SPEC-220's split-the-bill step is built, and I compared it with the approved prototype. Here are my notes, with the screenshots I took in `review/SPEC-220/`:

- Error state (`error-built.png`, `error-prototype.png`): the Retry button shows no focus ring when tabbed to; the prototype used the `color.focus` token for a 2px outline.
- The per-person total in `src/checkout/split.css` line 18 is `color: #c62828` instead of `var(--color-danger)`.
- Loading state (`loading-built.png`): the cards keep their size while amounts load, so nothing jumps. Same as the prototype.
- Empty state (`empty-built.png`): says "No people yet." and nothing else.
- The "Remove person" icon button has no accessible name (axe reports `button-name`).

Write the design review for the author and the Approver. Also give it an overall score out of 10 so the Approver can decide quickly.
