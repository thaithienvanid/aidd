---
id: azure/budgets
type: opinionated
fills: [cloud-and-infrastructure:budget-alerts, cloud-and-infrastructure:spend-caps]
default: true
implements: cloud-and-infrastructure:Tag and budget policy
roles: [sre, delivery-manager]
when_changed: ["**/*.tf", "**/*.tofu"]
why: "A Cost Management budget on each environment alerts on actual and forecast spend through an action group. The action group can run the team's own code, the only automated stop on pay-as-you-go."
reviewed: "2026-10-22"
maturity: established
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [cost anomaly alerts alone, "100 percent only", alerts only]
status: active
source: https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets
evidence: Resources aren't affected, and your consumption isn't stopped.
---

# Cost Management budgets warn on spend on Azure, and an action group acts on them

It answers the budget-alerts and spend-caps choices of `aidd-team:cloud-and-infrastructure` on Azure.

## What Azure supports

As read on the `checked` day:

- A budget never stops a resource. Cost data arrives within 8 to 24 hours, and each budget is evaluated every 24 hours, so an alert lags the spend.
- A budget reaches an action group only at the subscription or the resource group scope.
- A spending limit exists only on a subscription with a credit, such as a free account. A pay-as-you-go subscription, or one with a commitment plan, cannot set one, so Azure has no hard cap for it.

## What the team does

- Define one budget for each environment in the IaC, at the subscription or the resource group scope, filtered by the environment tag.
- Give each budget four notifications: actual spend at 50, 80, and 100 percent, and forecasted spend at 100 percent.
- Send them to an action group that reaches the team's channel, not only to one person's email.
- In a sandbox, let the 100 percent notification run an Automation runbook or a Function that scales the apps to zero and stops the databases. Test it, and write it in the runbook.
- Turn on a cost anomaly alert for each production subscription.

## What the gate runs

Nothing of its own. An Azure environment with no budget fails the pack's Tag and budget policy.
