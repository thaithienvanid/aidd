# SLO: {{title}}

Spec: [{{spec}}][spec]. Written {{today}}. A living doc (`frozen: false`): the SRE revises it after the release, and
later Specs link it too.
Owner: TODO: the SRE. Approvers: TODO: the product manager and the SRE. Revisit: YYYY-MM-DD.

<!-- One service level objective per row, each measured from what users experience. The Spec's `observe` block and
     rollback trigger read from it. An alert fires on the error budget burning, not on every failed request.
     The shape follows the Google SRE Workbook's example SLO document (https://sre.google/workbook/slo-document/).
     Write the prose at the `ste-80` level (the `aidd-team:plain-language` skill). -->

## Service overview

<!-- What the service does, for whom, and which user journeys these objectives protect, in three sentences. -->

TODO: the service and its users.

## SLIs and SLOs

| SLI | Target | Window | Error-budget policy | Alert | Owner | Review date |
| --- | --- | --- | --- | --- | --- | --- |
| TODO: share of requests answered under 300 ms, measured at the load balancer | 99.5% | 28 days rolling | The tiers in Error-budget policy | The rows in Alerts | TODO | YYYY-MM-DD |

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
     client's own errors, synthetic traffic), and the history of target changes with their reasons. -->

TODO: the measurement.

[spec]: {{spec_link}}
