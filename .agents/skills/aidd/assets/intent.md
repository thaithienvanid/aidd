---
aidd_version: "1.0.0"
type: intent
id: "{{id}}"
title: "{{title}}"
goal: "TODO: the metric and the number, by a date"
owner_team: "{{owner_team}}"
reaches: incremental
phases:
  - id: P1
    name: "TODO: Walking skeleton"
    slices:
      - {id: SPEC-TODO, title: "TODO: the thinnest path through the whole product"}
---

<!-- The work bigger than one Spec, which a person agrees to. Each slice is one line, and gets its Spec file when its
     work starts (`aidd new spec <ID>`). The fields: the aidd skill's `references/intents.md`. Write at the `ste-80`
     level (`aidd-team:plain-language`). -->

## Problem

<!-- Quote the brief, the person's own words, and name its file. Never rewrite it. Then who has the problem, the
     evidence (a link, a path, a quote with its source, or a dated note), and what they do today. Mark a guess
     "(assumed)". -->

TODO: the brief, quoted, and the problem.

## Outcome

<!-- `goal` with its baseline and date. It becomes a Spec's `hypothesis`. -->

TODO: the outcome.

## Who and what it touches

<!-- The users and their jobs, the teams, the systems, and the repositories. -->

TODO: who and what.

## Constraints

<!-- The appetite (the time this is worth, fixed, so the scope bends), the dates a person named, and the rules. -->

TODO: the constraints.

## Riskiest assumptions

<!-- Each assumption that would sink the outcome if false, and the first slice that tests it. Delete on a small Intent. -->

## Map

<!-- For discovery: one persona's journey today, each cell on evidence. Its opportunities become slices. Delete when
     the Intent needs none. -->

Persona or segment: TODO. Evidence: TODO, the sources, with dates.

| Part of the journey | TODO: 1 | TODO: 2 |
| --- | --- | --- |
| Goal and actions | TODO | TODO |
| Pain points, with a quote | TODO | TODO |
| Opportunities | TODO | TODO |
| Service blueprint: frontstage, backstage, support | TODO | TODO |

## Phases

<!-- Why the phases come in this order, and the exit criteria that end each one, the negative ones too. -->

### First slice

<!-- The slice that starts first carries its work now, so a builder can start it the day after agreement. Later slices
     stay one line until their work starts. -->

- Acceptance:
  - A1: TODO: one check that is true or false. Write 2 to 5 lines, numbered A1, A2, and so on.
- Order of work: TODO: the steps, in the order to build them.

### Large change

<!-- Only when a step cannot be undone, such as written data or a charged card. Else delete it. -->

- Point of no return: TODO: the first one-way step, and who approves passing it, or `none`.
- Safe stopping points: TODO: at least two slices after which the work can pause, consistent.
- Forward-fix plan: TODO: how you repair data after the point of no return.
- Target date: TODO: YYYY-MM-DD.
- Review date: TODO: YYYY-MM-DD, to go on, change the plan, or stop.
- Continuity reviewer: TODO: the one person who reviews every Spec of this Intent.

## Brief coverage

<!-- Each success criterion and each hard constraint of the brief, one row each, in its words or a faithful short form.
     "Covered by" names the proof, more than one comma-separated: the slice with its acceptance line (`SPEC-1 A3`, a
     line of `### First slice`), a later slice alone (its acceptance is written when it starts), or a phase's exit
     criterion (`exit: P1`). Name only a line that does what the row says. Or write `deferred, asked: <the question to
     the person>`, or `the brief's non-goal`. With no brief, write one line that says so and delete the table. -->

| Brief item | Covered by |
| --- | --- |
| TODO: a success criterion or hard constraint | TODO |

## Open questions

<!-- Each question only the person can answer, with your recommended answer. -->

none

## Perspectives

<!-- The Plan consult round's cards, and what the plan changed because of each. -->

| From | Assessment | Hard parts | Change made | Size |
| --- | --- | --- | --- | --- |
| architect | | | | |

## Out of scope

<!-- What no slice will do, and the nearby work a reader will think is included. -->

## Learn

<!-- At the end: whether the goal moved, which phase's order was wrong, and what to do differently. -->
