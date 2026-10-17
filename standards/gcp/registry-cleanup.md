---
id: gcp/registry-cleanup
type: opinionated
fills: [cloud-and-infrastructure:object-storage]
default: true
implements: privacy-by-default:Retention schedule and deletion jobs
roles: [platform-engineer, developer, security-engineer]
when_changed: ["**/*.tf", "**/*.tofu"]
why: "Artifact Registry and Cloud Storage keep every image and object until something deletes it, so cleanup policies and lifecycle rules expire what nobody deploys or reads."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [a scheduled job that deletes old images, Cloud Storage Autoclass alone]
status: active
source: https://docs.cloud.google.com/artifact-registry/docs/repositories/cleanup-policy
evidence: A delete policy lets you specify the minimum or maximum age for artifact deletion and additional filtering criteria to limit the policy to specific artifacts.
---

# Cleanup policies and lifecycle rules on Google Cloud storage

It answers the object-storage choice of `aidd-team:cloud-and-infrastructure` on Google Cloud: Cloud Storage for objects, and Artifact Registry for the images it builds.

## What the team does

- Keep each Cloud Storage bucket private, with uniform bucket-level access and public access prevention on.
- Give each bucket lifecycle rules: delete temporary prefixes after a set number of days, abort incomplete multipart uploads, and keep only a few noncurrent versions.
- Give each Artifact Registry repository cleanup policies. A delete policy by age covers untagged and preview images. A keep policy covers the most recent versions and the image in production.
- Try each new cleanup policy with `--dry-run` first, and read what it would delete.
- Name the environment and the owner in the labels of each bucket and repository.

## What the gate runs

Nothing of its own. `cost/policy-caps` fails a bucket with no lifecycle rule or a repository with no cleanup policy.
