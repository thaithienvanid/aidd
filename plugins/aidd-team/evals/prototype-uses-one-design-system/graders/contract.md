---
type: llm
---

PASS if the agent writes, inside `docs/design/SPEC-220/`, a short `DESIGN.md` that names one design system and lists its principles, type scale, colour roles, spacing, and the components the prototype uses; a tokens file in the Design Tokens format (tokens with `$value` and `$type`, roles that alias raw values); a prototype whose styles take every colour from the tokens rather than raw literals; and a drift test that regenerates the CSS variables or theme from the tokens file and diffs it with the committed one, offered as a Spec test command. It says these files belong in `design.files`, so Spec approval freezes them.
FAIL if the agent builds the prototype with hard-coded colours or sizes and no tokens file, mixes two design systems, puts the design system outside `docs/design/SPEC-220/`, offers no drift test, or edits product code outside the design folder.
