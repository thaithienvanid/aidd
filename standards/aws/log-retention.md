---
id: aws/log-retention
type: opinionated
fills: [observability:log-retention]
default: true
implements: observability:Retention
roles: [sre, reviewer]
when_changed: ["**/*.tf", "**/*.tofu"]
why: "CloudWatch Logs keeps log data forever unless a log group sets a retention, so storage grows every month that nobody reads it."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [the provider's default retention, an archive tier after the hot store]
status: active
source: https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/Working-with-log-groups-and-streams.html
evidence: "By default, log data is stored in CloudWatch Logs indefinitely."
---

# Every CloudWatch log group has a retention

It answers the log-retention choice of `aidd-team:observability` on AWS.

## What the team does

- Define each log group in the IaC with `retention_in_days`, before the function or service first writes to it. A group that a service creates on its own starts with no retention.
- Keep the period short: a few days in preview, and 30 days in production unless a regulation or the Spec names another.
- Export what an audit or a regulation must keep to S3, under `aws/s3-lifecycle`, rather than keep it in CloudWatch.
- Use the Infrequent Access log class for logs that are kept but rarely queried.
- Log the fact, not the payload, so the volume stays small.

## What the gate runs

Nothing of its own. `cost/policy-caps` fails a log group with no retention.
