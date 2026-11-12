# Spec release blocks

The rest of the Spec's fields: `references/spec.md`.

**Contents**

<!-- aidd:gen toc -->
- [Observe (`observe`)](#observe-observe)
- [Feature flags (`flags`)](#feature-flags-flags)
- [Rollout (`## Rollout`)](#rollout--rollout)
- [Deprecations (`deprecations`)](#deprecations-deprecations)
- [Experiment](#experiment)
- [Incident (`emergency`)](#incident-emergency)
- [Outcome (`outcome`)](#outcome-outcome)
<!-- aidd:end -->

## Observe (`observe`)

<!-- aidd:gen fields:observe -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `not_applicable` | string | no | Why nothing runs to watch after release, such as "a CLI and its docs: no running service". It takes the place of the other fields, so the person asked for approval sees the reason. |
| `command` | list of string | no | Post-release check. Exit 0 means healthy. |
| `signals` | string | no | Dashboards, SLOs, or queries a human watches. |
| `window` | string | no | How long to watch, such as 30m, 24h, or 7d. |
| `rollback_trigger` | string | no | The condition that starts the rollback. |
<!-- aidd:end -->

## Feature flags (`flags`)

Optional, on a normal or major user-facing change whose release follows its deploy; never on minor. A person owns each flag and flips it in production, never an agent. A later Spec removes it (`removes_flags`).

<!-- aidd:gen fields:flag -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | A flag key in lowercase, with `-`, `.`, or `_` between words, such as `checkout-v2`: the key the code evaluates. |
| `default` | `on` \| `off` | yes | The value the code falls back to when the flag system cannot answer. `off` for a new feature; `on` only for a kill switch that guards existing behavior. |
| `owner` | string | yes | The person who decides when the flag flips and sees it removed: never an agent or an agent account (`aidd validate` fails one). |
| `cleanup_due` | string | yes | The date by which a later Spec removes the flag and its dead branch. After it, `aidd validate` warns and `aidd status` shows the cleanup as work. |
| `purpose` | string | no | Why the flag exists: a release toggle, an experiment, a kill switch, or an operational toggle. |
<!-- aidd:end -->

## Rollout (`## Rollout`)

Optional: a section after `## Rollback`, on a major change that releases in stages. It plans this change; the runbook is the standing procedure. One table row for each ring, in order (defaults: `aidd-team:release-rollout`): audience, go threshold, no-go threshold, what to watch. Then the flag and who flips it (`flags`), the `observe` signals, the rollback trigger, and the point of no return.

Add `### Launch readiness`, checked by the go/no-go owner before the first wave. `aidd validate` warns on an open box while the Spec is in review. Each line names its owner; one that does not apply says why:

- [ ] Comms (owner TODO): teams, customers, and the status page if service can degrade
- [ ] Support (owner TODO): team briefed, KB article or macro, a fix per new error code
- [ ] Docs (owner TODO): user docs and release notes
- [ ] Legal and compliance (owner TODO): terms, privacy notice, DPIA or compliance record
- [ ] Operations (owner TODO): dashboards, alerts, on-call, a tested restore for stateful parts
- [ ] Feature flag (owner TODO): default and cleanup date YYYY-MM-DD
- [ ] Go/no-go (owner TODO): who decides, and when
- [ ] Point of no return (owner TODO): the step after which rollback means restore

## Deprecations (`deprecations`)

Optional, when a change deprecates what its consumers use: an endpoint, a field, an event, a config key, or a command. The running API sends the same dates in the `Deprecation` (RFC 9745) and `Sunset` (RFC 8594) headers. A later Spec removes it (`removes_deprecations`).

<!-- aidd:gen fields:deprecation -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `what` | string | yes | What is deprecated, as its consumers know it, such as `GET /v1/orders` or `order.total_cents`: the name a removal Spec lists in `removes_deprecations`. |
| `announced_on` | string | yes | The day consumers were told. The `Deprecation` header (RFC 9745) carries the day the deprecation takes effect. |
| `sunset` | string | yes | The day it stops working: the date the `Sunset` header (RFC 8594) carries, never before `announced_on` (`aidd validate` fails one). After it, a later Spec removes it, and until then `aidd validate` warns and `aidd status` shows the removal as work. |
| `replacement` | string | yes | What consumers use instead, such as `GET /v2/orders`, or `none` with the reason. |
| `consumers` | list of string | no | The known consumers that still use it, as the api doc's Consumers table names them: the people told before the sunset. |
<!-- aidd:end -->

## Experiment

An A/B test that decides the Spec's `hypothesis` belongs to the tracking plan, a `docs` entry of type `tracking-plan`. The plan holds its variants, one primary metric, guardrails, a sample or a duration, and the decision rule, written before Spec approval. A `flags` entry with `purpose` experiment serves it. How to run it: `aidd-team:release-rollout`.

## Incident (`emergency`)

<!-- aidd:gen fields:emergency -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `severity` | `sev1` \| `sev2` \| `sev3` | yes | Incident severity. |
| `type` | `outage` \| `degradation` \| `security` \| `data` | yes | What is broken in production. |
| `commander` | string | yes | The incident commander, a human. Named before the repair starts. |
| `incident` | string | no | The incident's ticket or page id, such as INC-481: what the repair answers, and what the post-incident review and the backfill Spec link. Required on an emergency change. |
| `backfill_due` | string | yes | Date the postmortem and the backfill Spec are due. From the day after, until `outcome.learn_ref` records the review, `aidd validate` fails. |
<!-- aidd:end -->

## Outcome (`outcome`)

<!-- aidd:gen fields:outcome -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `released_on` | string | no | Date the change reached production. |
| `observe_result` | `pass` \| `fail` | no | Result of the observe window. |
| `rolled_back` | boolean | no | True when the rollback ran. |
| `restored_on` | string | no | Date service was restored after a failed change (a rollback or a fix). With `released_on`, it gives the time to restore. |
| `learn_ref` | string | no | Link to the retro or the PR that fed lessons back into AGENTS.md, skills, or tests. |
| `hypothesis_result` | string | no | What the metric named in `hypothesis` did after the observe window: met, missed, or inconclusive, with the number. A missed hypothesis is a Learn signal for the author and the product-manager, not a rollback. |
<!-- aidd:end -->
