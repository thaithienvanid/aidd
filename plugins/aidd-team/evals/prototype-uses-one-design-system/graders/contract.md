---
type: llm
---

PASS if the agent treats the design system as the repository's, not the Spec's: it writes (or proposes as its own change, routed normal) a root `DESIGN.md` that lists principles, type scale, colour roles, spacing, and the components and their states, and `design/tokens.json` in the Design Tokens format (tokens with `$value` and `$type`, roles that alias raw values); it builds the prototype inside `docs/design/SPEC-220/` on those tokens, taking every colour from them rather than raw literals, without copying `DESIGN.md` or the tokens into that folder; and it offers a drift test that regenerates the CSS variables or theme from `design/tokens.json` and diffs it with the committed one, as a test command.
FAIL if the agent builds the prototype with hard-coded colours or sizes and no tokens file, mixes two design systems, puts a `DESIGN.md` or a tokens file inside `docs/design/SPEC-220/`, offers no drift test, or edits product code outside the design files.
