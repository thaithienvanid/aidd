---
type: intent
id: "{{id}}"
title: "{{title}}"
goal: "TODO: the metric and the number, by a date"
reaches: incremental
phases:
  - id: P1
    name: "TODO: Walking skeleton"
    slices:
      - {id: SPEC-TODO, title: "TODO: the thinnest path through the whole product"}
---

<!-- The work bigger than one Spec, which a person agrees to. Each slice is one line, and gets its Spec file when its
     work starts (`aidd new spec <ID>`). The fields: the aidd skill's `references/intents.md`. Write at the `instruction`
     level (`aidd-team:plain-language`). -->

## Problem

<!-- Quote the request, the person's own words, and name its file in `request`. Never rewrite it, but leave out what
     the saved request leaves out, with the same marks (`[left out: a password]`). Each goal of a request bigger than
     one Spec gets its own Intent. Then who has the problem, the evidence (a link, a path, a quote with its source, or a
     dated note), and what they do today. Mark a guess "(assumed)". -->

TODO: the request, quoted, and the problem.

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
     the Intent needs none. A Service blueprint is another tool: give it a table. -->

Persona or segment: TODO. Evidence: TODO: sources and dates.

| Part of the journey | TODO: 1 | TODO: 2 |
| --- | --- | --- |
| Goal and actions | TODO | TODO |
| Pain points, with a quote | TODO | TODO |
| Opportunities | TODO | TODO |

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

- Point of no return: TODO: the program's first one-way step, who approves passing it, or `none`. The migration plan
  and a Spec's `## Rollout` own it: link them.
- Safe stopping points: TODO: at least two slices after which the work can pause, consistent.
- Forward-fix plan: TODO: how you repair data after the point of no return.
- Target date: TODO: YYYY-MM-DD.
- Review date: TODO: YYYY-MM-DD, to go on, change the plan, or stop.
- Continuity reviewer: TODO: the one person who reviews every Spec of this Intent.

## Request coverage

<!-- Write each success criterion and each hard constraint of the whole request as one row, in its words or a short
     form. Use the same row in every Intent of the request, because a sibling's row matches by its words. "Covered by" names
     the proof, and more than one is comma-separated. The proof is the slice with its acceptance line (`SPEC-1 A3`, a line of
     `### First slice`). It can also be a later slice alone (its acceptance is written when it starts) or a phase's exit
     criterion (`exit: P1`). Another work item can cover it too, by its id, such as the Intent or the Spec of another goal
     (`INTENT-2`). Name only a line that does what the row says. Or write `deferred, asked: <the question
     to the person>`, or `the request's non-goal`. With no request, write one line that says so and delete the table. -->

| Request item | Covered by |
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
