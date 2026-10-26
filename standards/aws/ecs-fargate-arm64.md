---
id: aws/ecs-fargate-arm64
type: opinionated
fills: [cloud-and-infrastructure:serverless-compute]
default: false
implements: cloud-and-infrastructure:Provider map
roles: [architect, developer, sre, reviewer]
when_changed: ["**/*.tf", "**/*.tofu", Dockerfile, "task-definition*.json"]
why: "Amazon ECS on Fargate runs a steady or long-running container with no servers to manage, and on ARM64 (Graviton) it follows `cost/arm64-first`."
reviewed: "2026-10-22"
maturity: established
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [AWS Lambda on arm64, Fargate on x86_64, Amazon EKS]
status: active
source: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-arm64.html
evidence: You can run your applications on the platform that's powered by AWS Graviton Processors.
---

# Amazon ECS on Fargate runs the containers, on ARM64

It answers the serverless-compute choice of `aidd-team:cloud-and-infrastructure` on AWS, for a container that runs steadily or longer than a Lambda function may. aidd's default on AWS is `aws/lambda-arm64`.

## What Fargate supports

As read on the `checked` day: an ARM64 task needs the Linux operating system and Fargate platform version 1.4.0 or later. The `use1-az3` Availability Zone of US East (N. Virginia) runs no ARM64 task. AWS can stop a Fargate Spot task with a two-minute warning.

## What the team does

- Set `runtimePlatform` to `cpuArchitecture: ARM64` and `operatingSystemFamily: LINUX` in each task definition, and build the image for `linux/arm64` in CI.
- Give each service Application Auto Scaling with a minimum and a maximum task count, the maximum at what its database and its budget can take.
- Scale non-production services to zero tasks outside working hours, with a scheduled action.
- Run work that can stop and resume on the Fargate Spot capacity provider, and finish or hand off within two minutes of `SIGTERM`.
- Reach Amazon ECR, S3, and CloudWatch Logs through VPC endpoints before anyone adds a NAT gateway (`aws/no-default-nat`).
- Size each task's CPU and memory from a measured run.

## What the gate runs

Nothing of its own. `cost/policy-caps` fails an autoscaler with no maximum.
