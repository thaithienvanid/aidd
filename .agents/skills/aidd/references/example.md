# Worked example: rate-limit checkout

One team, one repo, profile `team`. Checkout already authenticates callers. The change limits each authenticated caller to 60 requests per 60-second window. Request 61 gets HTTP 429 and does not complete checkout.

## 1. The entry rule: the route

Every change starts here; it is the way into the loop, not a step of it. Before any code exists, `aidd new spec` computes the minimum route from the planned paths (once the branch has a diff, `aidd next` shows it):

```text
$ aidd new spec SPEC-220 --title "Rate-limit authenticated checkout" --type feat --owner-team checkout \
    --paths src/checkout/rate_limit/ --dimension availability
route: the minimum for these paths is normal (spec lane)
  - not minor: dimensions ['availability'] -> normal
specs/SPEC-220.md
next: replace the TODOs (Intent, Acceptance, Design, Rollback, the tests), write the test files, then `aidd validate specs/SPEC-220.md`
```

The client contract gains a 429 response, so it is not minor. No IAM, data, or protected path is touched, so it is not major. Confidence is high and `open_questions` is empty. The route is **normal**, and the planned paths are the first Task's scope.

## 2. Specify

`specs/SPEC-220.md` starts short (`--full` writes every section). The filled Spec:

````markdown
+++
aidd_version = "1.0.0"
kind = "spec"
id = "SPEC-220"
title = "Rate-limit authenticated checkout"
owner_team = "checkout"
type = "feat"
route = "normal"
confidence = "high"
open_questions = []
trace_id = "spec-220"
assisted_by = ["claude-code/claude-opus-5-5"]
rollback = "Revert the PR; the limiter keeps no persistent state."
residual_risk = "A caller over the limit waits until the window ends."

[risk]
summary = "Authenticated callers above 60 requests per 60 s get HTTP 429; everyone else is unchanged."
dimensions = ["availability"]
reversible = true

[[tasks]]
id = "TASK-220"
title = "Enforce the 60/60 limit"
scope = ["src/checkout/rate_limit/"]
assignee = "agent:claude-code"

[tests]
files = ["tests/checkout/test_rate_limit.py"]

[[tests.commands]]
name = "rate-limit"
command = ["pytest", "-q", "tests/checkout/test_rate_limit.py"]
new_behavior = true
covers = ["A1", "A2"]
+++

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

Each Acceptance item has an id, and the test command names the ids it proves in `covers`, so `aidd validate` warns if an item has no test. The test file is written now, before any implementation. On a draft PR holding only these two files, `aidd hash specs/SPEC-220.md --comment` prints `/aidd approve-spec SPEC-220 <32-hex hash> <commit>`. The checkout lead posts that comment. That is **Spec approval**.

## 3. Implement

The agent edits only `src/checkout/rate_limit/`. It does not touch the test file, whose hash is part of the approval. Its commits carry `Assisted-by: claude-code/claude-opus-5-5`.

## 4. Verify

```text
$ aidd test --spec specs/SPEC-220.md
[ok] green unit: passed (exit 0) log aidd-evidence/logs/green-unit.log
[ok] green rate-limit: passed (exit 0) log aidd-evidence/logs/green-rate-limit.log
[ok] red   rate-limit: failed (exit 1) log aidd-evidence/logs/red-rate-limit.log
evidence: aidd-evidence/evidence.json  head 5c1d0e7a9b2f
```

The config suite `unit` and the Spec's `rate-limit` both pass on head. `rate-limit` fails on base, so it proves the new behavior. The verification report starts with the head it checked, `5c1d0e7a9b2f`; a new push makes it stale, and Verify runs again. A failure would go back to Implement; this clean report hands the head to Review.

## 5. Review, Merge approval, and the merge

The PR description holds:

````markdown
```toml aidd
spec = "specs/SPEC-220.md"
```
````

In CI, `aidd-tests` uploads the evidence and `aidd-gate` re-derives everything. The gate stays pending until the checkout lead, who did not open the PR or author a commit, approves the head commit. Then `aidd/gate` turns green and the platform merges.

## When a second team joins

Platform also wants to edit `src/checkout/rate_limit/`. That turns on **Locks**: the later change waits, and they merge one at a time. If both teams own Specs under one Epic, **Multi-team** turns on: the Epic's `context` becomes the shared glossary, and cross-team `depends_on` uses `platform:SPEC-31`. While checkout is the only writer, both modules stay off.
