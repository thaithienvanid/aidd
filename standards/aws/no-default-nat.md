---
id: aws/no-default-nat
type: opinionated
fills: [cloud-and-infrastructure:egress-and-nat]
default: true
implements: cloud-and-infrastructure:Policy as code
roles: [architect, platform-engineer, security-engineer, reviewer]
when_changed: ["**/*.tf", "**/*.tofu"]
why: "A NAT gateway bills for every hour it exists and every gigabyte it carries, even for a quiet service, so a VPC gets one only when a design needs private compute to reach the internet."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [one shared NAT gateway, a NAT gateway per zone]
status: active
source: https://docs.aws.amazon.com/vpc/latest/userguide/nat-gateway-pricing.html
evidence: "When you provision a NAT gateway, you are charged for each hour that your NAT gateway is available and each gigabyte of data that it processes."
---

# No NAT gateway on AWS unless the design names it

It answers the egress-and-nat choice of `aidd-team:cloud-and-infrastructure` on AWS.

## What the team does

- Run a Lambda function outside a VPC unless it must reach a private resource, such as a database in a private subnet.
- Reach S3 and DynamoDB from a VPC through gateway endpoints, and other AWS services through interface endpoints, before anyone adds a NAT gateway.
- Add a NAT gateway only when the Spec's design names it and the reason, such as a third-party API that allows only fixed addresses.
- Give non-production environments one shared NAT gateway at most. Add one per zone only where production needs that availability.
- Tag each NAT gateway with the Spec that asked for it, so the policy can find it.
- Read VPC pricing on the day the design names a NAT gateway, and write the estimate in the Spec.

## What the gate runs

Nothing of its own. `cost/policy-caps` fails a plan that adds a NAT gateway without the Spec's tag.
