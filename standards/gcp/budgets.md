---
id: gcp/budgets
type: opinionated
fills: [cloud-and-infrastructure:budget-alerts]
default: true
implements: cloud-and-infrastructure:Tag and budget policy
roles: [platform-engineer, sre, delivery-manager]
when_changed: ["**/*.tf", "**/*.tofu"]
why: "A Cloud Billing budget on each environment alerts on actual and forecast spend, and its Pub/Sub notifications let code act on it, so a cost jump reaches a person within hours."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: ["the default 50, 90, and 100 percent rules", "100 percent only"]
status: active
source: https://docs.cloud.google.com/billing/docs/how-to/budgets
evidence: Setting an alerts-only budget doesn't automatically cap Google Cloud or Google Maps Platform usage or spending.
---

# Cloud Billing budgets warn on spend on Google Cloud

It answers the budget-alerts choice of `aidd-team:cloud-and-infrastructure` on Google Cloud.

## What Google Cloud supports

As read on the `checked` day: an alerts-only budget never caps. A spend cap budget can, for a few services (`gcp/hard-caps`). Costs reach Cloud Billing after a delay, so an alert lags the spend. A new budget's default rules are 50, 90, and 100 percent of actual spend.

## What the team does

- Define the budgets in the IaC, scoped to each environment's project or labels.
- Replace the default rules with four: actual spend at 50, 80, and 100 percent, and forecasted spend at 100 percent.
- Send the alerts to a monitoring channel the team reads, not only to the billing admins.
- Connect a Pub/Sub topic to each budget, so `gcp/hard-caps` can act on it.

## What the gate runs

Nothing of its own. A Google Cloud project with no budget fails the pack's Tag and budget policy.
