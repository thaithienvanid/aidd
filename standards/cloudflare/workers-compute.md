---
id: cloudflare/workers-compute
type: opinionated
fills: [cloud-and-infrastructure:serverless-compute]
default: true
implements: cloud-and-infrastructure:Provider map
roles: [architect, developer, platform-engineer, reviewer]
when_changed: [wrangler.jsonc, wrangler.json, wrangler.toml, "src/**"]
why: "Workers run each request in an isolate close to the user and start without a container, so a spiky or low-traffic service scales with no capacity plan. The Paid plan has a monthly base charge: read the pricing page before the estimate."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [Cloudflare Containers, Google Cloud Run, AWS Lambda]
status: active
source: https://developers.cloudflare.com/workers/platform/limits/
evidence: "On the Workers Paid plan, you can increase the maximum CPU time from the default 30 seconds to 5 minutes (300,000 ms)."
---

# Cloudflare Workers run the functions

It answers the serverless-compute choice of `aidd-team:cloud-and-infrastructure` on Cloudflare.

## What the team does

- Run HTTP handlers, cron triggers, and queue consumers as Workers. Move a job to Cloudflare Containers only when it needs a runtime, a binary, or more memory than an isolate gives.
- Set `compatibility_date` in the Wrangler file, and move it forward in its own change after you read the runtime's changelog.
- Reach other services through bindings (R2, D1, Queues, Hyperdrive, service bindings), never through a public URL with a key in the code.
- Store secrets with `wrangler secret put`, never in the Wrangler file.
- Turn on Workers Logs under `observability`, and lower `head_sampling_rate` when the volume grows.
- Set the caps of `cloudflare/workers-limits`.
- Check the limits page and the pricing page on the day a design depends on them, and write the date in the Spec.

## What the gate runs

Nothing of its own. `cloudflare/wrangler` builds every Worker in a dry run, and `cloudflare/workers-limits` checks its caps.
