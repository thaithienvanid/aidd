---
id: gcp/cloud-run
type: opinionated
fills: [cloud-and-infrastructure:serverless-compute]
default: true
implements: cloud-and-infrastructure:Provider map
roles: [architect, developer, platform-engineer, reviewer]
when_changed: ["**/*.tf", "**/*.tofu", Dockerfile, service.yaml]
why: "Cloud Run runs any container and serves many requests on one instance. With request-based billing and no minimum instances, it charges only while an instance handles requests, starts, or stops."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [Cloud Run functions, GKE Autopilot]
status: active
source: https://docs.cloud.google.com/run/docs/configuring/billing-settings
evidence: "If you choose request-based billing, you are charged per request and only when the instance processes a request."
---

# Google Cloud Run runs the containers

It answers the serverless-compute choice of `aidd-team:cloud-and-infrastructure` on Google Cloud.

## What Cloud Run supports

As read on the `checked` day: the container contract supports only the Linux x86_64 ABI, so a Cloud Run image is built for `linux/amd64`. The maximum instances setting can be exceeded for a short time during a traffic spike.

## What the team does

- Set `min-instances` to zero outside production. Keep a warm instance in production only when the Spec names the latency that needs it.
- Set `max-instances` on each service, at the most its database and its budget can take. Never rely on the default of 100.
- Set the request timeout to the longest a request should take, and the concurrency to the measured value, above one.
- Use request-based billing for spiky traffic. Read the pricing page before a switch to instance-based billing.
- Run batch work as Cloud Run jobs, with a task timeout and a retry limit.

## What the gate runs

Nothing of its own. `cost/policy-caps` fails a service with no maximum instances.
