---
id: aws/hard-caps
type: opinionated
fills: [cloud-and-infrastructure:spend-caps]
default: true
implements: cloud-and-infrastructure:Implement
roles: [architect, platform-engineer, sre, reviewer]
when_changed: ["**/*.tf", "**/*.tofu"]
why: "An AWS budget alert stops nothing, so the caps that stop a runaway cost are the limits on each resource, and a budget action or a spend limit where AWS offers one."
reviewed: "2026-10-16"
maturity: emerging
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [an automated action on a budget alert, alerts only]
status: active
source: https://docs.aws.amazon.com/accounts/latest/reference/create-spend-limit.html
evidence: "If your usage in a project reaches its limit, AWS pauses that project which stops its resources so your costs stay within it."
---

# Caps on each AWS resource, and a stop where AWS has one

It answers the spend-caps choice of `aidd-team:cloud-and-infrastructure` on AWS.

## What AWS supports

As read on the `checked` day:

- A spend limit for each project in AWS Settings. At the limit, AWS pauses the project and stops its resources. It is in limited release, needs the Paid Plan, covers at most 10 projects, and is built for sandbox work. AWS permanently deletes a paused project's data after 90 days without action.
- A budget action can apply an IAM policy or an SCP, or stop chosen EC2 and RDS instances. For any other service, it can only apply a policy.
- No other account-wide hard spending cap.

## What the team does

- Set reserved concurrency on each Lambda function, at the most the service and its database can take.
- Set a maximum throughput on each on-demand DynamoDB table (`aws/dynamodb-on-demand`).
- Set throttling on each API Gateway stage, and a usage plan for each API key.
- Set `maxReceiveCount` and a dead-letter queue on each SQS queue.
- In a sandbox account, add a budget action that applies a deny SCP at 100 percent, or the project spend limit where the account has it. Write the 90-day deletion in the runbook.

## What the gate runs

Nothing of its own. `cost/policy-caps` fails a resource with no cap.
