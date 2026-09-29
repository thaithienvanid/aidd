+++
aidd_version = "1.0.0"
kind = "initiative"
id = "{{id}}"
title = "{{title}}"
goal = "TODO: the metric and the number, not the feeling"
status = "draft"
owner_team = "{{owner_team}}"
+++

<!-- An Initiative holds Epics, so it carries the things an Epic must not decide alone: the portfolio
     order across teams, the shared budget of human attention, and the one goal every Epic under it
     is supposed to move. It has no `context` field by design — the glossary lives in the Epic
     (references/scale.md: "Stop when a second glossary appears: the terms go into the Epic"), and an
     Initiative that needs one has become an Epic. -->

## Outcome

<!-- Restate `goal` with its baseline and its date. If two Epics under this Initiative move the
     same number in opposite directions, the Initiative is the place that says which one wins. -->

## Epics

<!-- One row per child Epic, with the team that owns it and the order it lands in. The order is a
     decision about human attention, not about dependencies: never leave an Approver more open
     changes than they can decide today, so an Epic that would flood one team waits. -->

| Epic | Title | Owner team | Order | Why this order |
| --- | --- | --- | --- | --- |
| EPIC- | | | 1 | |

## Exit criteria

<!-- What makes this Initiative done, and how each line is checked. Include the negative criteria and
     a date; an Initiative with no end is a strategy document, and this is not that. -->

## Out of scope

<!-- What no Epic under this Initiative will do, and the adjacent programme a reader will confuse it
     with. -->

## Learn

<!-- Filled at the Initiative's end. Whether the goal moved, which Epic's ordering was wrong, and
     what the portfolio should stop funding. -->
