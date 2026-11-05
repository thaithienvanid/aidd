# Service: {{title}}

Started {{today}}. A living file, one per service (`aidd new service <name>`, in `docs/services/`). The SRE keeps it
current. Each Spec's SLO doc (`aidd new slo`) folds its objectives into this file in the same change, so the service's
objectives, alerts, and runbooks sit in one place.

Owner: TODO: the team. On call: TODO: the rotation or the contact. Revisit: YYYY-MM-DD.

<!-- One file per service that users or other services depend on. A Spec's SLO doc says what the change needs. This
     file says what the service promises now. Keep the shape of the SLO template: every target has a window, a budget
     policy, and an alert.
     Write the prose at the `ste-80` level (the `aidd-team:plain-language` skill). -->

## Overview

TODO: what the service does, for whom, and which user journeys its objectives protect, in three sentences.

## SLOs

| SLI | Target | Window | Error-budget policy | Alert | Owner | Review date | Spec |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TODO: share of requests answered under 300 ms | 99.5% | 28 days rolling | TODO: the tiers in the SLO doc | TODO: page or ticket | TODO | YYYY-MM-DD | SPEC-? |

## Runbooks

| Failure mode | Runbook | Last tested |
| --- | --- | --- |
| TODO | TODO: `docs/runbooks/<ID>.md` | YYYY-MM-DD |

## Dependencies

| Depends on | Why | When it fails |
| --- | --- | --- |
| TODO | TODO | TODO: the fallback, or "the service stops" |

## Changes

| Date | Spec | What changed in the objectives, and why |
| --- | --- | --- |
| {{today}} | TODO | TODO |
