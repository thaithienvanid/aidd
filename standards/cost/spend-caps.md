+++
id = "cost/spend-caps"
type = "opinionated"
fills = ["cloud-and-infrastructure:spend-caps"]
default = true
implements = "cloud-and-infrastructure:Implement"
roles = ["architect", "platform-engineer", "sre", "reviewer"]
when_changed = ["**/*.tf", "**/*.tofu", "wrangler.jsonc", "wrangler.json", "wrangler.toml"]
why = "An alert only tells a person, often a day late, so every resource that can scale carries its own cap, and a sandbox carries a stop that ends all spend."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "emerging"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
alternatives = ["an automated action on a budget alert", "per-service limits", "alerts only"]
status = "active"
source = "https://developers.cloudflare.com/billing/manage/budget-alerts/"
evidence = "Budget alerts notify you by email when your account-wide usage-based spend crosses a dollar threshold you define."
+++

# A cap on each resource, and a stop for each sandbox

It answers the spend-caps choice of `aidd-team:cloud-and-infrastructure` for a provider with no standard of its own here. On AWS, Google Cloud, and Cloudflare, use the provider's standard.

## What each provider supports

As read on the `checked` day, and kept in each provider's standard:

| Provider | Hard spending cap | The stop it offers |
| --- | --- | --- |
| Cloudflare | none for the account | limits on each Worker, queue, and AI Gateway (`cloudflare/workers-limits`) |
| AWS | a spend limit for each project, in limited release | budget actions (`aws/hard-caps`) |
| Google Cloud | spend cap budgets for a few services, in Preview | a budget notification that runs the team's own shutdown code (`gcp/hard-caps`) |

## What the team does

- Give each resource that scales the cap the pack's Implement row asks for, at what the service, its database, and its budget can take.
- Give each sandbox and preview account the provider's strongest stop, and say in the runbook what it deletes.
- Never put a stop that deletes resources on production. There, the stop is `cost/kill-switch`.
- Read the provider's billing page again at each review. A new hard cap changes this table.

## What the gate runs

Nothing of its own. `cost/policy-caps` runs the cap policies where the IaC is OpenTofu or Terraform.
