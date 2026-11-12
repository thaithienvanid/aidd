# Service: {{title}}

Started {{today}}. A living file, one per service (`aidd new service-card <name>`, in `docs/services/`). The SRE keeps it
current. It is the service's living SLO document: it owns the current objectives, the error-budget policy, and the
alerts. A Spec's SLO doc (`aidd new slo`) is a frozen delta, and the SRE folds the approved delta into this file in the
same change. So the objectives, alerts, and runbooks sit in one place.

Owner: TODO: the team. Revisit: YYYY-MM-DD.
Status: TODO: draft or approved. Approved on: YYYY-MM-DD, by TODO.

<!-- One file per service that users or other services depend on. A Spec's SLO doc says what the change moves. This
     file says what the service promises now. The shape follows the Google SRE Workbook's example SLO document
     (https://sre.google/workbook/slo-document/): every target has a window, a budget policy, and an alert. Each SLI
     is measured from what users experience. The Spec's `observe` block and rollback trigger read from it. An alert
     fires on the error budget burning, not on every failed request.
     Write the prose at the `instruction` level (the `aidd-team:plain-language` skill). -->

## Overview

TODO: what the service does, for whom, and which user journeys its objectives protect, in three sentences.

## SLOs

| SLI | Target | Window | Error-budget policy | Alert | Owner | Review date | Spec |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TODO: share of requests answered under 300 ms | 99.5% | 28 days rolling | TODO: the tiers in Error-budget policy | TODO: the rows in Alerts | TODO | YYYY-MM-DD | SPEC-? |

## Rationale

<!-- Why each target is the number it is: the period it was measured over and what users saw, or "picked, not yet
     checked against user experience" until it is. A target set above what the service does today is a plan, not an
     objective. -->

TODO: the measurement behind each target.

## Error-budget policy

<!-- Defaults: change them to fit. Agree them with the product manager before the budget is spent, so the team applies
     the policy and does not argue it under pressure. The budget is 100% minus the target. At 99.5% over 28 days, that
     is about 3.4 hours of full failure. -->

| Budget | Releases (change to fit) |
| --- | --- |
| Healthy: no burn-rate alert is open, and budget is left | Normal releases. |
| Burning: a page or a ticket from Alerts is open | Each release needs a go from the SLO owner. |
| Spent: no budget is left in the window | Only fixes and reliability work land, until the budget recovers. |

## Alerts

<!-- Multiwindow, multi-burn-rate defaults from the Google SRE Workbook, "Alerting on SLOs", table 5-8
     (https://sre.google/workbook/alerting-on-slos/), checked 2026-10-09. A burn rate of 1 spends the whole budget in
     exactly one window. An alert fires only when the long and the short window both burn faster than the rate. So it
     stops soon after recovery. The short window is 1/12 of the long one. For a 30-day budget, a page means 2% or 5% of
     it is gone, and a ticket means 10%. Change the rates to fit. -->

| Severity | Burn rate | Long window | Short window | Goes to |
| --- | --- | --- | --- | --- |
| Page | 14.4× | 1 h | 5 m | On-call, at any hour |
| Page | 6× | 6 h | 30 m | On-call, at any hour |
| Ticket | 1× | 3 days | 6 h | The owner, the next working day |

## Clarifications and caveats

<!-- How each SLI is measured (the query or the dashboard), what it leaves out and why (planned maintenance, a
     client's own errors, synthetic traffic). -->

TODO: the measurement.

## On-call

<!-- Who answers when this service pages. Link the team's paging tool and rota instead of copying them. The runbooks
     below link here for it. An agent never pages or acknowledges a page. -->

- Rota: TODO: the schedule's link, the rotation length, and the hours it covers (business hours or 24/7)
- Escalation: TODO: primary, then secondary after N minutes without an acknowledgement, then the service owner
- Handover: TODO: when shifts change, and what the outgoing person hands over (open incidents, silenced alerts, risky changes in flight)
- Paging policy: TODO: the link to what pages a person (an SLO burn or a symptom) and what only opens a ticket

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
