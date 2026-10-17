---
id: aws/dynamodb-on-demand
type: opinionated
fills: [cloud-and-infrastructure:database]
default: true
implements: cloud-and-infrastructure:Implement
roles: [architect, developer, data-engineer, reviewer]
when_changed: ["**/*.tf", "**/*.tofu"]
why: "DynamoDB in on-demand mode charges for each request and nothing for idle capacity, and a maximum throughput on each table caps a surge, so a new key-value workload starts cheap and bounded."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [DynamoDB provisioned capacity with auto scaling, PostgreSQL (managed) on Amazon RDS or Aurora]
status: active
source: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/on-demand-capacity-mode.html
evidence: "By configuring throughput, you can keep table-level usage and costs bounded, protect against an inadvertent surge in consumed resources, and prevent excessive use for predictable cost management."
---

# DynamoDB on demand holds key-value data on AWS

It answers the database choice of `aidd-team:cloud-and-infrastructure` on AWS, for an access pattern that fits a key-value store. Relational data stays on a managed PostgreSQL.

## What the team does

- Create each new table in on-demand mode. Move a table to provisioned capacity only when its traffic is steady and the worksheet shows the saving.
- Set a maximum read and write throughput on each table and each global secondary index. A request above it is throttled, which caps the bill.
- Write the access patterns in the Spec before the keys. Each query the code runs names its key or index.
- Set a TTL attribute on items that expire, such as sessions and tokens.
- Turn on point-in-time recovery for data that must be restored, and rehearse the restore in the runbook.

## What the gate runs

Nothing of its own. `cost/policy-caps` fails an on-demand table with no maximum throughput.
