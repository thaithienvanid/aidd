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

The route (`references/routes.md`) sets the lane. Before any code exists, `aidd risk` gives the least route for the planned paths:

```text
$ aidd risk --paths src/checkout/rate_limit/ --change-type feat
route: normal (Spec first)
areas: none
edit level: allow
first step: write the Spec and its tests: aidd new spec "<title>" --paths src/checkout/rate_limit/
```

`aidd new spec` writes the same route, with the planned paths as the first Task's scope:

```text
$ aidd new spec SPEC-220 --title "Rate-limit authenticated checkout" --change-type feat --paths src/checkout/rate_limit/
specs/SPEC-220.md
next: replace the TODOs (Request, Context, Acceptance, Design, Rollback, the tests), write the test files, then `aidd validate -- specs/SPEC-220.md`
```

The client contract gains a 429 response, so it is not minor, and the agent declares the `availability` dimension. No area that raises the route to major is touched. Confidence is high and `open_questions` is empty. The route is **normal**, and the planned paths are the first Task's scope.

## 2. Specify

`specs/SPEC-220.md` starts short (`--full` writes every section). The filled Spec:

````markdown
---
type: spec
id: SPEC-220
title: Rate-limit authenticated checkout
change_type: feat
status: draft
route: normal
rollback: Revert the PR; the limiter keeps no persistent state.

risk:
  summary: Authenticated callers above 60 requests per 60 s get HTTP 429; everyone else is unchanged.
  dimensions: [availability]
  irreversible: false
  residual: A caller over the limit waits until the window ends.

tasks:
  - id: TASK-220
    title: Enforce the 60/60 limit
    scope: [src/checkout/rate_limit/]
    assignee: role:developer

tests:
  files: [tests/checkout/test_rate_limit.py]

  commands:
    - name: rate-limit
      command: [pytest, -q, tests/checkout/test_rate_limit.py]
      new_behavior: true
      covers: [A1, A2]
---

## Request

> "Stop one caller from flooding checkout: cap each signed-in caller at 60 requests a minute, and tell them when they hit it." (the checkout lead, in the ticket)

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

Each Acceptance item has an id. The test command names the ids it proves in `covers`, so `aidd validate` warns if an item has no test. The agent writes the acceptance test file now, before any implementation. It sets `status: ready`, commits the two files on `spec/SPEC-220`, and asks: "Approve SPEC-220? It caps each signed-in caller at 60 checkout requests a minute, proven by A1 and A2." The checkout lead answers "yes, go ahead". The agent sets `status: approved`, `approved_by: "@checkout-lead"`, and `approved_at`, and commits with `Approved-by: @checkout-lead`. That is **Spec approval**.

### When the change needs more than the Spec

This change is normal and small, so the Spec is enough. Had it been major (a new shared limiter service, say), the architect would add a tech spec. It holds the design in depth, the alternatives, the cross-cutting concerns, and the pre-mortem. The SRE would add a `## Rollout` section to the Spec (`references/spec-release.md`).

```text
$ aidd new tech-spec rate-limits --spec SPEC-220
specs/SPEC-220/tech-spec-rate-limits.md
linked from specs/SPEC-220.md as a frozen `docs` entry: Spec approval pins it with the Spec
```

The Spec gains a `docs` entry for the tech spec, which is approved with the Spec, so an edit after approval is `spec.revise`. The Spec itself stays short.

## 3. Implement

The agent edits only `src/checkout/rate_limit/`. It does not touch the test file, which the approval covers. Its commits carry `Assisted-by: claude-code/claude-opus-5-5`.

## 4. Verify

```text
$ aidd test --spec specs/SPEC-220.md
[ok] green unit: passed (exit 0) log .aidd/evidence/logs/green-unit.log
[ok] green rate-limit: passed (exit 0) log .aidd/evidence/logs/green-rate-limit.log
[ok] red   rate-limit: failed (exit 1) log .aidd/evidence/logs/red-rate-limit.log
evidence: .aidd/evidence/evidence.json  head 5c1d0e7a9b2f
```

The config suite `unit` and the Spec's `rate-limit` both pass on head. `rate-limit` fails on base, so it proves the new behavior. The verification report starts with the head it checked, `5c1d0e7a9b2f`. A new push makes it stale, and Verify runs again. The verifier then calls checkout 61 times as one caller and sees A1 and A2 hold. A failure would go back to Implement. This clean report lets the review of that head count.

## 5. Review, Merge approval, and the merge

The reviewer reads the diff against the Spec and finds nothing to fix. Under `team`, on the platform, the agent pushes `spec/SPEC-220` (its own branch: allow), opens the PR (`pr.open`: report), sets `status: in_review`, and stops. It says: "Opened the PR for SPEC-220; it waits for your review." In CI, `aidd test` runs again on the head. The checkout lead, who did not author a commit, reviews and approves the PR, and the branch protection lets it merge. That review is **Merge approval**.

## When a second team joins

Platform also wants to edit `src/checkout/rate_limit/`. That turns on **Locks**: the later change waits, and the changes merge one at a time. If both teams own slices of one Intent, **Multi-team** turns on. The Intent's `context` becomes the shared glossary, and cross-team `blocked_by` uses `platform:SPEC-31`. While checkout is the only writer, both modules stay off.
