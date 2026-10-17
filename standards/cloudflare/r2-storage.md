---
id: cloudflare/r2-storage
type: opinionated
fills: [cloud-and-infrastructure:object-storage]
default: true
implements: privacy-by-default:Retention schedule and deletion jobs
roles: [architect, developer, platform-engineer, security-engineer]
when_changed: [wrangler.jsonc, wrangler.json, wrangler.toml, "**/*.tf"]
why: "R2 has an S3-compatible API and charges nothing for data read out to the internet, so files that users download often cost only their storage and operations."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [Amazon S3, Google Cloud Storage]
status: active
source: https://developers.cloudflare.com/r2/pricing/
evidence: "Egressing directly from R2, including via the Workers API, S3 API, and r2.dev domains does not incur data transfer (egress) charges and is free."
---

# Cloudflare R2 holds the files and objects

It answers the object-storage choice of `aidd-team:cloud-and-infrastructure` on Cloudflare.

## What the team does

- Keep each bucket private. Reach it from a Worker binding, or give a client a presigned URL that expires in minutes.
- Turn off the `r2.dev` address for production. Serve a public bucket only through a custom domain, so the cache and the WAF apply.
- Add object lifecycle rules with `wrangler r2 bucket lifecycle add`: expire temporary uploads and exports by prefix. R2 already expires an unfinished multipart upload after seven days, so keep that rule.
- Move an object to Infrequent Access only when it is read rarely and kept long. Read the minimum duration and the retrieval charge on the pricing page first.
- Name each bucket by environment, and give each environment its own bucket and its own API token.

## What the gate runs

Nothing of its own. `wrangler r2 bucket lifecycle list <bucket>` shows the rules a reviewer checks.
