+++
id = "cost/alert-thresholds"
type = "opinionated"
fills = ["cloud-and-infrastructure:budget-alerts"]
default = true
implements = "cloud-and-infrastructure:Implement"
roles = ["platform-engineer", "sre", "delivery-manager", "product-manager"]
when_changed = ["**/*.tf", "**/*.tofu"]
why = "Three alerts on actual spend give the team time to act before the budget is gone, and an alert on the forecast warns in the first days of a month that will end over it."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
alternatives = ["100 percent only", "an anomaly alert on daily spend"]
status = "active"
source = "https://docs.cloud.google.com/billing/docs/how-to/budgets"
evidence = "Forecasted cost threshold rules send notifications when the forecasted cost (calculated out to the end of the current calendar budget period) exceeds the threshold amount."
+++

# Budget alerts at 50, 80, and 100 percent, and on the forecast

It answers the budget-alerts choice of `aidd-team:cloud-and-infrastructure` for a provider with no standard of its own here, such as Azure. On AWS, Google Cloud, and Cloudflare, the provider's standard holds the same thresholds: `aws/budgets-anomaly`, `gcp/budgets`, and `cloudflare/budget-alerts`.

## What the team does

- Give the pack's budget for each environment four alerts: actual spend at 50, 80, and 100 percent, and forecast spend at 100 percent, where the provider forecasts.
- Send every alert to the team's channel, and name in the runbook who reads it and what they do.
- Read the budgets each month, and change one only in a reviewed change.
- Treat an alert as a warning. The stop is the provider's spend-caps standard.

## What the gate runs

Nothing of its own. The pack's Tag and budget policy checks that each environment has a budget.
