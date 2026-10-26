---
aidd_version: "1.0.0"
kind: epic
id: "{{id}}"
title: "{{title}}"
goal: "TODO: the metric and the number, not the feeling"
owner_team: "{{owner_team}}"
context: "TODO: the shared terms and constraints every Spec under this Epic inherits"
reaches: incremental
specs: []
---

<!-- `reaches`: incremental (each Spec merges by itself), flagged (each behind a flag, off, until the `launch` Spec), or batched
     (it must land at once: `aidd goal open` cuts goal/<id>). `specs`: the planned Spec ids, in landing order.
     An Epic exists to sequence and bound a set of Specs. So it carries the things a Spec must not decide alone: the
     order, the exit criteria, what is permanently out, and the one glossary. Specs under it with two or more
     `owner_team`s turn on Multi-team (references/scale.md). When a second glossary appears, stop and move the terms
     up here.
     Write the prose at the `ste-80` level (the `aidd-team:plain-language` skill). -->

## Outcome

<!-- Restate `goal` with its baseline and date: what is measured, what it is today, what it
     must reach, and by when. A goal nobody can measure is a title, not a goal. -->

## Product brief (PRD-lite, optional)

<!-- For an Epic a product manager must justify before the Specs: one short block, not a PRD. Delete it when the
     Initiative's `## Brief` already says this. -->

- Problem and evidence: TODO: who has the problem, and the quote, number, or lost deal that shows it.
- Users and jobs: TODO: who uses it, and the job each one hires it for.
- Journeys or story map: TODO: the steps a user takes, left to right, and which Spec delivers each.
- Appetite: TODO: the time this is worth, fixed; the scope bends to fit it.
- Non-goals: TODO: what this Epic will not do.
- Rabbit holes: TODO: the parts that could swallow the appetite, and the decision that avoids each.

| Outcome metrics | Baseline | Target | Date |
| --- | --- | --- | --- |
| TODO | TODO | TODO | YYYY-MM-DD |

## Specs

<!-- One row per child Spec, in the order they land. `depends_on` inside a Spec orders Tasks. This table orders
     changes, and says why the order is what it is. A row with no Spec id yet is a placeholder for work you have
     assessed but not specified. Keep those rows: they are the plan. -->

| Spec | Title | Route | Depends on | Why this order |
| --- | --- | --- | --- | --- |
| SPEC- | | | — | |

## Large change

<!-- Plan how the work stops and recovers before the first Spec lands. A flag cannot undo written data, sent
     messages, charged cards, or published events. Keep each line short. -->

- Point of no return: TODO: the first step that a flag or a rollback cannot undo, and the person who approves passing it. Write `none` and the reason if no step is one-way.
- Safe stopping points: TODO: at least two Spec rows after which the work can pause and the system stays consistent.
- Forward-fix plan: TODO: how you repair data and behavior if something goes wrong after the point of no return.
- Target date: TODO: YYYY-MM-DD, when the Epic must meet its exit criteria.
- Review date: TODO: YYYY-MM-DD, when you check the plan and decide to go on, change it, or stop.
- Continuity reviewer: TODO: the one person who reviews every Spec under this Epic, so the steps do not drift from the goal.

## Exit criteria

<!-- What makes this Epic done, and how you check each line. It is distinct from `goal`. The goal is the number that
     moves. The exit criteria are the conditions that let you stop. Include the negative ones. A criterion such as
     "no open finding older than N days" is what stops an Epic running forever. -->

## Out of scope

<!-- What will never be a Spec under this Epic, and the thing a reader will assume is included. This
     is the Epic-level Non-goals: it stops the tenth Spec that quietly doubles the Epic. -->

## Learn

<!-- Fill this in at the Epic's end, not per Spec. Say what the ordering taught you, which exit criterion was wrong,
     and what the next Epic should do differently. A Spec's `## Learn` records its own lesson. This section records
     the lesson about the decomposition. -->
