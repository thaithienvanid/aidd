---
id: aws/lambda-arm64
type: opinionated
fills: [cloud-and-infrastructure:serverless-compute]
default: true
implements: cloud-and-infrastructure:Provider map
roles: [architect, developer, platform-engineer, reviewer]
when_changed: ["**/*.tf", "**/*.tofu", template.yaml, serverless.yml]
why: "Lambda runs short, spiky work with no server to idle, and on arm64 (Graviton) the same function gets better price and performance than on x86_64, so it is the default for event-driven work on AWS."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [AWS Fargate, Lambda on x86_64]
status: active
source: https://docs.aws.amazon.com/lambda/latest/dg/foundation-arch.html
evidence: Lambda functions that use arm64 architecture (AWS Graviton2 processor) can achieve significantly better price and performance than the equivalent function running on x86_64 architecture.
---

# AWS Lambda on arm64 runs the functions

It answers the serverless-compute choice of `aidd-team:cloud-and-infrastructure` on AWS.

## What the team does

- Set `architectures: ["arm64"]` on every function. Use x86_64 only when a dependency, a layer, or an extension has no arm64 build, and write which one in the Spec.
- Build the deployment package or the container image for `linux/arm64` in CI, and run the tests on that architecture.
- Set the function's timeout to the longest a request should take, never the maximum Lambda allows.
- Size the memory from a measured run, such as AWS Lambda Power Tuning, not from a guess.
- Set the concurrency cap that `aws/hard-caps` describes.
- Move a steady, long-running service to Fargate when the break-even worksheet says so.

## What the gate runs

Nothing of its own. `cost/policy-caps` fails a function with no concurrency cap, and `iac/opentofu` checks the configuration.
