+++
aidd_version = "1.0.0"
kind = "epic"
id = "{{id}}"
title = "{{title}}"
goal = "TODO: the metric and the number, not the feeling"
status = "draft"
owner_teams = ["{{owner_team}}"]
context = "TODO: the shared terms and constraints every Spec under this Epic inherits"
+++

<!-- An Epic exists to sequence and bound a set of Specs, so it carries the things a Spec must not
     decide alone: the order, the exit criteria, what is permanently out, and the one glossary.
     Two or more `owner_teams` turns on Multi-team (references/scale.md); when a second glossary
     appears, stop and move the terms up here. -->

## Outcome

<!-- Restate `goal` with its baseline and its date: what is measured, what it is today, what it
     must reach, and by when. A goal nobody can measure is a title, not a goal. -->

## Specs

<!-- One row per child Spec, in the order they land. `depends_on` inside a Spec orders Tasks; this
     table orders changes, and says why the order is what it is. A row with no Spec id yet is a
     placeholder for work you have assessed but not specified — keep those, they are the plan. -->

| Spec | Title | Route | Depends on | Why this order |
| --- | --- | --- | --- | --- |
| SPEC- | | | — | |

## Exit criteria

<!-- What makes this Epic done, and how each line is checked. Distinct from `goal`: the goal is
     the number that moves, the exit criteria are the conditions that let you stop. Include the
     negative ones — a criterion that says "no open finding older than N days" is what stops an Epic
     running forever. -->

## Out of scope

<!-- What will never be a Spec under this Epic, and the thing a reader will assume is included. This
     is the Epic-level Non-goals: it stops the tenth Spec that quietly doubles the Epic. -->

## Learn

<!-- Filled at the Epic's end, not per Spec. What the ordering taught you, which exit criterion was
     wrong, and what the next Epic should do differently. A Spec's `## Learn` records its own lesson;
     this records the lesson about the decomposition. -->
