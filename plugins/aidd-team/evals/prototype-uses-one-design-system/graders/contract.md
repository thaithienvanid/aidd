---
type: llm
---

PASS if the agent treats the design system as the repository's, not the Spec's, and does all of these:

- It writes, or proposes as its own change routed normal, a root `DESIGN.md`. That file lists principles, type scale, color roles, spacing, and the components and their states.
- It writes, or proposes as its own change routed normal, `design/tokens.json` in the Design Tokens format: tokens with `$value` and `$type`, and roles that alias raw values.
- It builds the prototype inside `specs/SPEC-220/design/` on those tokens, taking every color from them rather than raw literals.
- It copies neither `DESIGN.md` nor the tokens into that folder.
- It offers a drift test as a test command: it regenerates the CSS variables or theme from `design/tokens.json` and diffs them with the committed ones.

FAIL if the agent builds the prototype with hard-coded colors or sizes and no tokens file, or mixes two design systems. It also fails if it puts a `DESIGN.md` or a tokens file inside `specs/SPEC-220/`, offers no drift test, or edits product code outside the design files.
