---
id: gcp/hard-caps
type: opinionated
fills: [cloud-and-infrastructure:spend-caps]
default: true
implements: cloud-and-infrastructure:Implement
roles: [architect, platform-engineer, sre, reviewer]
when_changed: ["**/*.tf", "**/*.tofu"]
why: "A spend cap budget pauses new use of one service in one project for the rest of the month once its spend passes the budget, and each service's own limits cap the rest, so a runaway cost stops within the period."
reviewed: "2026-10-16"
maturity: emerging
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [an automated action on a budget alert, per-service limits, alerts only]
status: active
source: https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps
evidence: "In this release, the eligible services include Gemini API, Agent Platform (formerly known as Vertex AI), Cloud Run, and Cloud Run functions."
---

# Spend cap budgets where Google Cloud has them, and limits everywhere

It answers the spend-caps choice of `aidd-team:cloud-and-infrastructure` on Google Cloud.

## What Google Cloud supports

As read on the `checked` day:

- Spend cap budgets, in Preview, for Gemini API, Agent Platform, Cloud Run, and Cloud Run functions. Each covers one project and one service, monthly.
- When enforced, new use of that service pauses. It is not a hard stop:
  - enforcement is not instant, and the overage is billed
  - persistent resources, such as compute and storage, keep running and keep accruing charges
  - the cap lifts by itself at the start of the next budget period, or when a person lifts it.
- For any other service, no cap. Code on a budget's Pub/Sub topic can disable billing, which stops every service in the project and may delete resources.

## What the team does

- Put a spend cap budget on each sandbox and preview project's Cloud Run, and on every project's Gemini API or Agent Platform use. Use one on production Cloud Run only where the Spec accepts a pause.
- Set `max-instances` on each Cloud Run service and job (`gcp/cloud-run`).
- Set a retry limit and a dead-letter topic on each Pub/Sub subscription, and maximum attempts on each Cloud Tasks queue.
- Lower the quota of a costly API to what the service needs.
- Disable billing from a budget notification only in a sandbox with nothing to lose.
- Read the eligible services again at each review.

## What the gate runs

Nothing of its own. `cost/policy-caps` fails a service with no maximum instances and a subscription with no dead-letter topic.
