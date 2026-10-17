---
id: aws/s3-lifecycle
type: opinionated
fills: [cloud-and-infrastructure:object-storage]
default: true
implements: privacy-by-default:Retention schedule and deletion jobs
roles: [architect, developer, platform-engineer, security-engineer]
when_changed: ["**/*.tf", "**/*.tofu"]
why: "S3 keeps every object until someone deletes it, so a lifecycle configuration on each bucket expires what nobody needs and moves rarely read data to a cheaper class without anyone remembering to."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [S3 Intelligent-Tiering alone, Cloudflare R2]
status: active
source: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html
evidence: "S3 Lifecycle helps you store objects cost effectively throughout their lifecycle by transitioning them to lower-cost storage classes, or, deleting expired objects on your behalf."
---

# Every S3 bucket has a lifecycle configuration

It answers the object-storage choice of `aidd-team:cloud-and-infrastructure` on AWS.

## What the team does

- Keep S3 Block Public Access on for the account and every bucket. Serve public files through CloudFront.
- Give every bucket a lifecycle configuration with at least these rules:
  - expire temporary prefixes, such as uploads and exports, after a set number of days
  - abort incomplete multipart uploads after a few days
  - expire noncurrent versions where versioning is on.
- Add a transition rule only for large objects kept a long time. Each transition is a billed request, and some classes have a minimum storage duration.
- Name the bucket's environment and owner in its tags.

## What the gate runs

Nothing of its own. `cost/policy-caps` fails a bucket with no lifecycle configuration.
