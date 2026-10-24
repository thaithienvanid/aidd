---
id: azure/log-retention
type: opinionated
fills: [observability:log-retention]
default: true
implements: observability:Retention
roles: [sre, reviewer]
when_changed: ["**/*.tf", "**/*.tofu"]
why: "A Log Analytics workspace bills for each gigabyte it ingests and for retention past the included period. So each workspace sets its retention and a daily cap, and verbose tables use a cheaper plan."
reviewed: "2026-10-22"
maturity: established
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [the provider's default retention, an archive tier after the hot store]
status: active
source: https://learn.microsoft.com/en-us/azure/azure-monitor/logs/data-retention-configure
evidence: By default, all tables in a Log Analytics workspace retain data for 30 days, except for log tables with 90-day default retention.
---

# Every Log Analytics workspace has a set retention and a daily cap

It answers the log-retention choice of `aidd-team:observability` on Azure.

## What Azure supports

As read on the `checked` day: the ingestion price includes 31 days of analytics retention, so a shorter period saves nothing. Analytics retention can grow to two years, and long-term retention keeps data past it for less. Once a daily cap is reached, data collection stops until the workspace's reset hour, and the alerts that read it go blind.

## What the team does

- Define each workspace in the IaC with `retention_in_days`, even when it keeps the default, so the choice is written down.
- Set `daily_quota_gb` on each workspace as a safeguard, well above a normal day, and an alert on ingestion below it.
- Point Application Insights at the workspace, with sampling, so traces do not fill the cap.
- Move verbose tables that nobody queries, such as container logs, to the Basic or Auxiliary plan.
- Keep what an audit or a regulation needs in long-term retention, or export it to Blob Storage under a lifecycle rule.

## What the gate runs

Nothing of its own. `cost/policy-caps` fails a workspace with no daily cap.
