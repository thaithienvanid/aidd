# Worked example: rate-limit checkout

One team, one repo, profile `team`. Checkout already authenticates callers. The change limits each authenticated caller to 60 requests per 60-second window. Request 61 gets HTTP 429 and does not complete checkout.

**Contents**

<!-- aidd:gen toc -->
- [1. Before the first edit: the route](#1-before-the-first-edit-the-route)
- [2. Specify](#2-specify)
- [3. Implement](#3-implement)
- [4. Verify](#4-verify)
- [5. Review, Merge approval, and the merge](#5-review-merge-approval-and-the-merge)
- [When a second team joins](#when-a-second-team-joins)
<!-- aidd:end -->

## 1. Before the first edit: the route

The route (`references/routes.md`) sets the lane; asking for it is not a step of the loop. Before any code exists, the gate forecasts the minimum route from the planned paths:

```text
$ aidd gate --paths src/checkout/rate_limit/ --dimension availability
Route: normal (spec lane), needed by the planned paths (1 path)
  - not minor: dimensions ['availability'] -> normal

Next for this change:
1. the spec lane: this change needs a Spec, approved before any code
   who: agent
   how: write the Spec and its tests first: `aidd new spec <ID> --title "..." --paths src/checkout/rate_limit/`
A forecast: it records nothing. On the branch, the gate computes the route again from the real diff, and can only raise it.
```

Once the branch has a diff, `aidd gate` computes the route of the change again. `aidd new spec` computes the same route as the preview and writes it, with the planned paths as the first Task's scope:

```text
$ aidd new spec SPEC-220 --title "Rate-limit authenticated checkout" --type feat --owner-team checkout \
    --paths src/checkout/rate_limit/ --dimension availability
route: the minimum for these paths is normal (spec lane)
  - not minor: dimensions ['availability'] -> normal
specs/SPEC-220.md
next: replace the TODOs (Intent, Context, Acceptance, Design, Rollback, the tests), write the test files, then `aidd validate specs/SPEC-220.md`
```

The client contract gains a 429 response, so it is not minor. No IAM, data, or protected path is touched, so it is not major. Confidence is high and `open_questions` is empty. The route is **normal**, and the planned paths are the first Task's scope.

## 2. Specify

`specs/SPEC-220.md` starts short (`--full` writes every section). The filled Spec:

````markdown
---
aidd_version: "1.0.0"
kind: spec
id: SPEC-220
title: Rate-limit authenticated checkout
owner_team: checkout
type: feat
route: normal
confidence: high
open_questions: []
trace_id: spec-220
assisted_by: [claude-code/claude-opus-5-5]
rollback: Revert the PR; the limiter keeps no persistent state.
residual_risk: A caller over the limit waits until the window ends.

risk:
  summary: Authenticated callers above 60 requests per 60 s get HTTP 429; everyone else is unchanged.
  dimensions: [availability]
  reversible: true

tasks:
  - id: TASK-220
    title: Enforce the 60/60 limit
    scope: [src/checkout/rate_limit/]
    assignee: agent:claude-code

tests:
  files: [tests/checkout/test_rate_limit.py]

  commands:
    - name: rate-limit
      command: [pytest, -q, tests/checkout/test_rate_limit.py]
      new_behavior: true
      covers: [A1, A2]
---

## Context

Checkout lives in src/checkout. The auth middleware already sets request.caller.

## Non-goals

Unauthenticated traffic and per-IP limits.

## Acceptance

```gherkin
Scenario: A1 requests within the limit complete as today
  Given an authenticated caller of the checkout API
  When that caller sends 60 requests in one 60-second window
  Then all 60 complete as today

Scenario: A2 the 61st request is refused
  Given an authenticated caller who has sent 60 requests in this window
  When that caller sends request 61
  Then it returns HTTP 429 and does not complete checkout
```
````

Each Acceptance item has an id. The test command names the ids it proves in `covers`, so `aidd validate` warns if an item has no test. The agent writes the test file now, before any implementation. On a draft PR holding only these two files, `aidd hash specs/SPEC-220.md --line` prints `/aidd approve-spec SPEC-220 <32-hex hash> <commit>`. The checkout lead posts that comment. That is **Spec approval**.

### When the change needs more than the Spec

This change is normal and small, so the Spec is enough. Had it been major (a new shared limiter service, say), the architect would add a tech spec. It holds the design in depth, the alternatives, the cross-cutting concerns, and the pre-mortem. The SRE would add the rollout runbook:

```text
$ aidd new tech-spec rate-limits --spec SPEC-220
specs/SPEC-220/tech-spec-rate-limits.md
linked from specs/SPEC-220.md as a frozen `docs` entry: Spec approval pins it with the Spec
$ aidd new runbook RB-7 --title "Roll out the checkout limiter" --spec SPEC-220
```

The Spec gains one `docs` entry each. The tech spec is frozen with the Spec, whose hash covers it, so an edit after approval voids the approval. The runbook is living (`frozen: false`), since it stays current after the merge. The Spec itself stays short.

## 3. Implement

The agent edits only `src/checkout/rate_limit/`. It does not touch the test file, whose hash is part of the approval. Its commits carry `Assisted-by: claude-code/claude-opus-5-5`.

## 4. Verify

```text
$ aidd test --spec specs/SPEC-220.md
[ok] green unit: passed (exit 0) log .aidd/evidence/logs/green-unit.log
[ok] green rate-limit: passed (exit 0) log .aidd/evidence/logs/green-rate-limit.log
[ok] red   rate-limit: failed (exit 1) log .aidd/evidence/logs/red-rate-limit.log
evidence: .aidd/evidence/evidence.json  head 5c1d0e7a9b2f
```

The config suite `unit` and the Spec's `rate-limit` both pass on head. `rate-limit` fails on base, so it proves the new behavior. The verification report starts with the head it checked, `5c1d0e7a9b2f`. A new push makes it stale, and Verify runs again. A failure would go back to Implement. This clean report hands the head to Review.

## 5. Review, Merge approval, and the merge

The PR description holds:

````markdown
```yaml aidd
spec: specs/SPEC-220.md
```
````

In CI, `aidd-tests` uploads the evidence and `aidd-gate` re-derives everything. The gate stays pending until the checkout lead, who did not open the PR or author a commit, approves the head commit. Then `aidd/gate` turns green and the platform merges.

## When a second team joins

Platform also wants to edit `src/checkout/rate_limit/`. That turns on **Locks**: the later change waits, and the changes merge one at a time. If both teams own Specs under one Epic, **Multi-team** turns on. The Epic's `context` becomes the shared glossary, and cross-team `depends_on` uses `platform:SPEC-31`. While checkout is the only writer, both modules stay off.
