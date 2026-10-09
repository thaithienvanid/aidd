+++
id = "aws/budgets-anomaly"
type = "opinionated"
fills = ["cloud-and-infrastructure:budget-alerts"]
default = true
implements = "cloud-and-infrastructure:Tag and budget policy"
roles = ["platform-engineer", "sre", "delivery-manager"]
when_changed = ["**/*.tf", "**/*.tofu"]
why = "AWS Budgets alerts on actual and forecast spend for each environment, and Cost Anomaly Detection catches a spike that no fixed threshold expected, so a cost jump reaches a person within a day."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
alternatives = ["Cost Anomaly Detection alone", "100 percent only"]
status = "active"
source = "https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-best-practices.html"
evidence = "You can set budgets to alert against either actual values or forecasted values."
+++

# AWS Budgets and Cost Anomaly Detection warn on spend

It answers the budget-alerts choice of `aidd-team:cloud-and-infrastructure` on AWS.

## What AWS supports

As read on the `checked` day: billing data reaches Budgets at least once a day, so an alert lags the spend. A forecast alert needs about five weeks of usage before it can fire.

## What the team does

- Define the budgets in the IaC, filtered by the environment tag or by the environment's account.
- Give each budget four alerts: actual spend at 50, 80, and 100 percent, and forecast spend at 100 percent.
- Send each alert to an SNS topic that reaches the team's channel, not only to one person's email.
- Turn on Cost Anomaly Detection with an AWS managed monitor for AWS services, and an individual-alert subscription.
- Write in the runbook who reads an alert and what they do next.

## What the gate runs

Nothing of its own. A budget missing from an AWS environment fails the pack's Tag and budget policy.
