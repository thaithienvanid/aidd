---
aidd_version: "1.0.0"
type: spec
id: "{{id}}"
title: "{{title}}"
owner_team: "{{owner_team}}"
change_type: "{{change_type}}"    # feat, fix, refactor, perf, docs, test, build, ci, chore, deps, infra, data, security, compliance
route: "{{route}}"                # normal or major; never below what `aidd risk --paths` gives
confidence: high                  # high, medium, low (low: stop and ask)
open_questions: []                # facts still unknown; empty when high
trace_id: "{{trace_id}}"
assisted_by: []                   # "harness/model" for each agent that writes code or tests
rollback: Revert the change.      # name the steps if a revert is not enough

risk:
  summary: "TODO: who or what behaves differently after this change"
  dimensions: []                  # data, security, privacy, financial, compliance, availability, third_party, cost, performance
  reversible: true                # false when a revert cannot restore the prior state (forces major)
# cost_estimate: {monthly: "40 EUR", at_10x: "300 EUR", source: "infracost diff"}   # with infrastructure or a cost risk

tasks:
  - id: "{{id}}-T1"
    title: "TODO: the first slice"
    scope: ["src/TODO/"]          # the globs this Task's diff may change; never a test file

tests:
  files: ["tests/TODO"]           # fixed at Spec approval: the test files, and the config they run through
  commands:
    - name: acceptance
      command: ["TODO"]           # a vector, one argument per item; never a shell string
      new_behavior: true          # feat and fix: fails on base (red), passes on head (green); false otherwise
      covers: [A1]                # the Acceptance ids this command proves
---

<!-- The short Spec: enough for Spec approval on a normal change. `aidd new spec --full` adds Problem, Goals, Non-goals, and
     Learn; a major Spec gets them by default. The tech spec it links holds the alternatives, the cross-cutting concerns, and
     the pre-mortem; its runbook holds the rollout. After approval, an edit between the --- lines is spec.revise. `aidd validate`
     errors on a placeholder left in a scope, tests.files, or a command. Write at the `ste-80` level (`aidd-team:plain-language`). -->

## Intent

<!-- The originator's own words, quoted: the problem, the outcome they want, and what must not change. -->

TODO: quote the request.

## Context

<!-- Why, the files involved and their patterns, the constraints, the non-goals, and each assumption you could not verify. -->

TODO: the context.

## Acceptance

<!-- One behavior per item, each starting with its id (A1, ...), which `covers` lists. Observable: "request 61 returns 429".
     On a hot path, one item is its budget: a percentile, a load, an environment, and the rows today and at 10x. -->

- A1: TODO: given ..., when ..., then ...

## Design

<!-- A few lines: the approach, and the files and functions it changes. Adopt mature software before building, or say why. -->

TODO: the approach.

## Policy conflicts

<!-- Where specialist input, a domain pack, or company rules clash, and who decides; never pick a side. -->

none

## Rollback

<!-- How to undo it, beyond `rollback` above, and what a revert cannot restore. -->

TODO: how to undo it.
