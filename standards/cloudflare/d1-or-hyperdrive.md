---
id: cloudflare/d1-or-hyperdrive
type: opinionated
fills: [cloud-and-infrastructure:database]
default: true
implements: cloud-and-infrastructure:Database connection pool
roles: [architect, developer, reviewer]
when_changed: [wrangler.jsonc, wrangler.json, wrangler.toml, "migrations/**"]
why: "D1 lets a project keep many small serverless SQLite databases, such as one for each tenant, at no extra cost for the isolation, and Hyperdrive pools the connections to an existing PostgreSQL, so a Worker never opens one for each request."
reviewed: "2026-10-16"
maturity: emerging
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [PostgreSQL (managed) without Hyperdrive, Durable Objects with SQLite storage]
status: active
source: https://developers.cloudflare.com/d1/
evidence: "D1 allows you to create thousands of databases at no extra cost for isolation, perfect for scaling out application vibe-coding platforms."
---

# D1, or PostgreSQL through Hyperdrive, holds the data on Cloudflare

It answers the database choice of `aidd-team:cloud-and-infrastructure` on Cloudflare.

## What the team does

- Choose D1 when the data splits into many small databases, such as one for each tenant, and SQLite's SQL is enough. Read the size limit on the limits page first, and write it in the Spec.
- Choose PostgreSQL behind Hyperdrive when the data is one large relational store, or when it already lives in PostgreSQL. Read the database's own connection limit, and size the pool below it.
- Keep each D1 schema change in `migrations/`, applied with `wrangler d1 migrations apply`. Apply it to the preview database before production.
- Turn off Hyperdrive's query cache for a query whose result must be fresh.
- Restore a D1 database to an earlier point with Time Travel, and rehearse it in the restore runbook.

## What the gate runs

Nothing of its own. The migration checks of `aidd-team:schema-migration` run on each change under `migrations/`.
