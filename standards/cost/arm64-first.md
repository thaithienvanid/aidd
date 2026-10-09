+++
id = "cost/arm64-first"
type = "opinionated"
fills = ["cloud-and-infrastructure:compute-architecture"]
default = true
implements = "cloud-and-infrastructure:Break-even worksheet"
roles = ["architect", "platform-engineer", "developer"]
when_changed = ["Dockerfile", "**/*.tf", "**/*.tofu", ".github/workflows/**"]
why = "AWS states that arm64 Lambda functions get better price and performance than x86_64, so functions and containers start on arm64 where the platform and every dependency allow it, and the team measures the result."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
alternatives = ["x86-64 only", "both, built for each"]
status = "active"
source = "https://docs.aws.amazon.com/lambda/latest/dg/foundation-arch.html"
evidence = "Lambda functions that use arm64 architecture (AWS Graviton2 processor) can achieve significantly better price and performance than the equivalent function running on x86_64 architecture."
+++

# arm64 first, where the platform and the dependencies allow

It answers the compute-architecture choice of `aidd-team:cloud-and-infrastructure`.

## Where each platform stands

As read on the `checked` day:

- AWS Lambda and Fargate run arm64 (Graviton). `aws/lambda-arm64` sets it.
- Google Cloud Run supports only x86-64, so its images are `linux/amd64`.
- Cloudflare Workers run on Cloudflare's own machines, with no choice to make.

## What the team does

- Check each native dependency, layer, and agent for an arm64 build before the move, and write a missing one in the Spec.
- Build images with `docker buildx build --platform` for the architectures the service runs on, and run the tests on each.
- Compare the cost and the latency of both builds in the first week, and record the result in the Spec.
- Read each provider's pricing page on the day of the decision. No price is kept here.

## What the gate runs

Nothing of its own. `cost/policy-caps` can fail a Lambda function that is not arm64 and names no reason.
