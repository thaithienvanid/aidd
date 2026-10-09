+++
id = "cost/kill-switch"
type = "opinionated"
fills = ["release-rollout:cost-kill-switch"]
default = true
implements = "release-rollout:Rollback rehearsal"
roles = ["sre", "platform-engineer", "delivery-manager"]
when_changed = ["docs/runbooks/**"]
why = "When cost or harm runs away, the team needs one tested way to stop the path in minutes, without a deploy, so the stop is a runbook rehearsed like a rollback."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
alternatives = ["a kill-switch flag on the expensive path", "a provider budget action that stops the resources"]
status = "active"
source = "https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html"
evidence = "To intentionally throttle a function, set its reserved concurrency to 0. This stops your function from processing any events until you remove the limit."
+++

# A tested runbook cuts the costly path

It answers the cost kill-switch choice of `aidd-team:release-rollout`.

## What the team does

- Write the runbook with `aidd new runbook <id> --title "Kill switch: <service>"`. Name the alert or the bill that sends someone to it, and the person who may run it.
- Give one copy-ready step for each platform the service runs on:
  - AWS Lambda: set reserved concurrency to 0
  - Cloud Run: set its ingress to internal, or move all traffic to a static revision
  - Cloudflare Workers: turn the costly path off with a flag, or remove its route
  - a model call: turn off the feature flag on the costly path, or lower the gateway's spend limit.
- Write the step that turns each one back on, and the check that shows the service is healthy again.
- Rehearse it in staging each quarter, and record `tested_on`. `aidd doctor` warns when the drill is older than `runbook_max_age_days`.
- A person runs it in production. An agent proposes the step and never runs it.

## What the gate runs

Nothing of its own. `aidd doctor` reports a runbook that has not been tested lately.
