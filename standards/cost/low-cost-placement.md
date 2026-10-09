+++
id = "cost/low-cost-placement"
type = "opinionated"
fills = ["cloud-and-infrastructure:hosting-target"]
default = true
implements = "cloud-and-infrastructure:Pick the placement"
roles = ["architect", "product-manager", "platform-engineer"]
when_changed = ["**/*.tf", "**/*.tofu", "wrangler.jsonc", "wrangler.json", "wrangler.toml", "Dockerfile"]
why = "The owner's preferred order, not a measured ranking: start on the platform that needs the least to run, and move down only when the workload asks for it and the break-even worksheet shows it."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "emerging"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
alternatives = ["the provider a company policy names", "Google Cloud first", "AWS first"]
status = "active"
source = "https://developers.cloudflare.com/workers/platform/pricing/"
evidence = "There are no additional charges for data transfer (egress) or throughput (bandwidth)."
+++

# Cloudflare first, then Cloud Run, then AWS

It answers the hosting-target choice of `aidd-team:cloud-and-infrastructure` for a new project. It is the owner's preference, so no stack includes it: a company's org preset requires it, or replaces it with its own standard through `[standards_policy] replace`.

## The order

1. **Cloudflare** (`cloudflare-serverless`, `cloudflare-fullstack`) when the service fits a Worker: HTTP and event work, short CPU per request, data in R2, D1, or PostgreSQL behind Hyperdrive. Workers charge no egress, and the Paid plan has a monthly base charge.
2. **Google Cloud Run** (`gcp-run`) when it needs a container: a runtime, a binary, or long requests that a Worker cannot run.
3. **AWS** (`aws-serverless`) when it needs a service that only AWS offers, or the client already runs on AWS.

## What the team does

- Fill the pack's break-even worksheet for the chosen platform and the next one in the order. Write the line that decided it in the Spec.
- Read each provider's pricing page on the day of the decision, and write the date beside each figure. No price is kept here.
- Move down the order only for a reason the Spec names, never by habit.

## What the gate runs

Nothing of its own. `aidd validate` warns when the Spec has no monthly estimate.
