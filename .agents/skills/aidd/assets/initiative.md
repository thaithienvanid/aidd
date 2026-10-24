---
aidd_version: "1.0.0"
kind: initiative
id: "{{id}}"
title: "{{title}}"
goal: "TODO: the metric and the number, not the feeling"
owner_team: "{{owner_team}}"
---

<!-- An Initiative holds Epics. So it carries the things an Epic must not decide alone:
     - the portfolio order across teams
     - the shared budget of human attention
     - the one goal that every Epic under it is supposed to move.
     It has no `context` field by design: the glossary lives in the Epic (references/scale.md: "Stop when a second
     glossary appears: the terms go into the Epic"). An Initiative that needs one has become an Epic.
     Write the prose at the `ste-80` level (the `aidd-team:plain-language` skill). -->

## Brief

<!-- The one-page pitch this Initiative answers, before any Spec: a solo founder's MVP starts here too
     (`aidd new initiative`). The shape of a Shape Up pitch: a problem worth solving, how much time it is worth, a rough
     solution, and what is out. Keep it to one page. Each Spec under it carries its own Acceptance. -->

- Problem: TODO: who has it, the evidence (a quote, a number, a lost deal), and what they do today instead.
- Appetite: TODO: the time this is worth, fixed (such as two weeks for one person); the scope bends to fit it.
- Solution sketch: TODO: the places, the affordances, and the connections between them, rough on purpose.
- Rabbit holes: TODO: the parts that could swallow the appetite, and the decision that avoids each.
- No-gos: TODO: what this will not do, so nobody builds it by accident.
- Success metric: TODO: the one number that says it worked, its baseline, the target, and the date to check. It
  becomes a Spec's `hypothesis` (and a tracking plan, `aidd new analytics`).

### Journey

<!-- For discovery, when the Initiative changes how people get something done. Map one persona or segment and one
     journey, from what they do today, before anyone designs the solution. Each cell rests on evidence (an interview,
     a support ticket, a session recording, a metric). Mark a guess "(assumed)". The opportunities become Epics or
     Specs. Delete this subsection when the Initiative needs none. -->

Persona or segment: TODO. Scenario: TODO. Evidence: TODO, the sources, with dates.

| Stage | TODO: stage 1 | TODO: stage 2 | TODO: stage 3 |
| --- | --- | --- | --- |
| Goal and actions | TODO | TODO | TODO |
| Touchpoints | TODO: web, app, email, phone | TODO | TODO |
| Pain points, with a quote | TODO | TODO | TODO |
| Opportunities | TODO | TODO | TODO |
| Service blueprint: frontstage, backstage, support processes | TODO | TODO | TODO |

## Outcome

<!-- Restate `goal` with its baseline and its date. If two Epics under this Initiative move the
     same number in opposite directions, the Initiative is the place that says which one wins. -->

## Epics

<!-- One row per child Epic, with the team that owns it and the order it lands in. The order is a decision about
     human attention, not about dependencies. Never leave an Approver more open changes than they can decide today.
     So an Epic that would flood one team waits. -->

| Epic | Title | Owner team | Order | Why this order |
| --- | --- | --- | --- | --- |
| EPIC- | | | 1 | |

## Perspectives

<!-- The Plan consult round (`/aidd-team:plan`): each card the architect, the designer, the security engineer, or the
     domain expert returned on the draft, and what the plan changed because of it. A disagreement left open is a question for the
     author, with a recommended answer. -->

| From | Assessment | Hard parts | Change made | Size |
| --- | --- | --- | --- | --- |
| architect | | | | |

## Exit criteria

<!-- What makes this Initiative done, and how you check each line. Include the negative criteria and a date. An
     Initiative with no end is a strategy document, and this is not that. -->

## Out of scope

<!-- What no Epic under this Initiative will do, and the adjacent programme a reader will confuse it
     with. -->

## Learn

<!-- Fill this in at the Initiative's end. Say whether the goal moved, which Epic's ordering was wrong, and what the
     portfolio should stop funding. -->
