---
id: cost/policy-caps
type: opinionated
fills: [cloud-and-infrastructure:policy-tool]
default: true
implements: cloud-and-infrastructure:Policy as code
roles: [platform-engineer, security-engineer, architect, reviewer]
when_changed: ["**/*.tf", "**/*.tofu", "policy/**"]
why: "Conftest runs OPA policies over the plan before the merge, so a resource that can scale, retry, or log without a bound is refused before it exists, not found on the bill."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [Kyverno (Kyverno JSON for a plan), Checkov custom policies, HashiCorp Sentinel]
status: active
source: https://github.com/open-policy-agent/conftest
evidence: "Using Conftest you can write tests for your Kubernetes configuration, Tekton pipeline definitions, Terraform code, Serverless configs or any other config files."
enforced_by:
  - name: caps
    command: [conftest, test, --policy, policy/cost, plan.json]
---

# Policies refuse an uncapped resource in the plan

It answers the policy-tool choice of `aidd-team:cloud-and-infrastructure`, with Conftest, the pack's default, at the version its Policy as code row names.

## The policies

Keep them in `policy/cost/`, in Rego, each with a test. Each one denies:

- a scalable resource with no cap: a Lambda function without reserved concurrency, a Cloud Run service without maximum instances, an autoscaler without a maximum, an on-demand DynamoDB table without a maximum throughput
- a queue or subscription without a retry limit and a dead-letter queue: SQS and Pub/Sub
- a log group or log bucket without a retention
- a bucket without a lifecycle rule, and an image repository without a cleanup policy
- a NAT gateway without the tag that names the Spec which asked for it.

## What the team does

- Write `plan.json` in CI with `tofu show -json` on the saved plan. A project only on Cloudflare has no plan; `cloudflare/workers-limits` and `cloudflare/queues-workflows` check its Wrangler file instead.
- Allow an exception only by a tag or a field that names the Spec, never by a skipped policy.
- Run `conftest verify` on the policies' own tests.

## What the gate runs

One `tests` entry runs `conftest test --policy policy/cost plan.json`. A denied resource fails the change.
