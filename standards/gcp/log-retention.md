---
id: gcp/log-retention
type: opinionated
fills: [observability:log-retention]
default: true
implements: observability:Retention
roles: [platform-engineer, sre, reviewer]
when_changed: ["**/*.tf", "**/*.tofu"]
why: "Cloud Logging keeps each log for its bucket's retention period, and a longer period or a larger volume costs more, so every bucket names its period and the noisiest logs are excluded before they are stored."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [the provider's default retention, an archive tier after the hot store]
status: active
source: https://docs.cloud.google.com/logging/docs/buckets
evidence: "If you don't customize the retention period, the default is 30 days."
---

# Every Cloud Logging bucket has a set retention

It answers the log-retention choice of `aidd-team:observability` on Google Cloud.

## What the team does

- Set the retention of each project's `_Default` bucket in the IaC, even when it keeps the default, so the choice is written down.
- Add exclusion filters to the `_Default` sink for logs nobody reads, such as health checks and successful static requests.
- Route the logs that an audit or a regulation must keep to a user-defined bucket, or to Cloud Storage under `gcp/registry-cleanup`, with their own retention.
- Leave the `_Required` bucket alone. Its retention is fixed.
- Log the fact, not the payload, so the volume stays small.

## What the gate runs

Nothing of its own. `cost/policy-caps` fails a log bucket with no retention.
