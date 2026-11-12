# SLO delta: {{title}}

Spec: [{{spec}}][spec]. Written {{today}}. Frozen at Spec approval with the Spec: it holds only what this change adds,
changes, or retires in a service's objectives.
Owner: TODO: the SRE. Approvers: TODO: the product manager and the SRE.
The service card (`aidd new service-card <name>`, in `docs/services/`) holds the objectives the service promises now,
with the error-budget policy and the alerts. The SRE folds this delta into it in the same change.

<!-- One row per service level objective this change moves, each measured from what users experience. The Spec's
     `observe` block and rollback trigger read from it. The shape follows the Google SRE Workbook's example SLO document
     (https://sre.google/workbook/slo-document/). Never copy the card's current objectives here, so a target has one home.
     Write the prose at the `instruction` level (the `aidd-team:plain-language` skill). -->

## Service

<!-- The service this delta is for, by its card (`docs/services/<name>.md`), and which user journeys the changed
     objectives protect, in two sentences. -->

TODO: the service and its users.

## SLI changes

<!-- Change: add, tighten, loosen, or retire. Was: the target on the card now, or "none". Why: one line for the change.
     The card owns the Rationale behind each number and the Clarifications on how an SLI is measured, so fold what this
     change adds to them into the card with the delta. -->

| SLI | Change | Was | Becomes | Window | Alert | Review date | Why |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TODO: share of requests answered under 300 ms, measured at the load balancer | add | none | 99.5% | 28 days rolling | TODO: a row of the card's Alerts | YYYY-MM-DD | TODO |

## Budget policy and alerts

<!-- The card's error-budget policy and alert rows apply unless this change differs. Say which row differs and why. -->

The service card's, unchanged.

[spec]: {{spec_link}}
