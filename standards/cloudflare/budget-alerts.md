---
id: cloudflare/budget-alerts
type: opinionated
fills: [cloud-and-infrastructure:budget-alerts]
default: true
implements: cloud-and-infrastructure:Implement
roles: [sre, delivery-manager]
when_changed: [wrangler.jsonc, wrangler.json, wrangler.toml]
why: "Cloudflare's budget alerts email the team when the account's usage-based spend crosses a dollar amount, so three alerts at 50, 80, and 100 percent of the month's budget give warning before the end of the bill."
reviewed: "2026-10-16"
maturity: emerging
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: ["100 percent only", usage notifications for each product]
status: active
source: https://developers.cloudflare.com/billing/manage/budget-alerts/
evidence: Budget alerts are available to Pay-as-you-go accounts only. Enterprise contract accounts are not supported.
---

# Budget alerts at 50, 80, and 100 percent on Cloudflare

It answers the budget-alerts choice of `aidd-team:cloud-and-infrastructure` on Cloudflare.

## What Cloudflare supports

As read on the `checked` day:

- Budget alerts for Pay-as-you-go accounts only. An Enterprise contract account has none.
- One threshold for each alert, in dollars, on the account's usage-based spend in the billing period. There is no alert on a forecast.
- Email only. An alert never pauses or caps usage.

## What the team does

- Create three budget alerts on each account: at 50, 80, and 100 percent of its monthly budget, each as a dollar amount.
- Send each alert to a shared address that reaches the team, not to one person.
- Give production its own account where the spend matters, because an alert covers the whole account.
- Read the billable usage dashboard each week, since nothing warns on a forecast.
- Keep the caps of `cloudflare/workers-limits` as the stop. An alert is a warning.
- Name the person in the runbook who acts on an alert, and the first step they take.

## What the gate runs

Nothing of its own. The alerts live in the dashboard, not in the Wrangler file.
