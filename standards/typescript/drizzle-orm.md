---
id: typescript/drizzle-orm
type: opinionated
fills: [schema-migration:orm]
default: true
implements: schema-migration:Model drift check
roles: [developer, data-engineer, reviewer]
when_changed: ["**/schema.ts", "**/schema/**", drizzle.config.ts, "migrations/**", "drizzle/**", package.json]
why: "Drizzle declares tables in TypeScript and types each query from them, close to SQL and with no runtime code generator, and it runs on Node.js and on edge runtimes such as Cloudflare Workers with D1."
reviewed: "2026-10-16"
maturity: emerging
tool:
  name: drizzle-orm
  registry: npm
  package: drizzle-orm
version_policy: current_stable
checked_version: "0.45.4"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://registry.npmjs.org/-/package/drizzle-orm/dist-tags
evidence: "\"latest\":\"0.45.4\""
alternatives: [Prisma, Kysely, TypeORM]
status: active
---

# Drizzle maps the TypeScript code to the database

It answers the orm choice of `aidd-team:schema-migration`. License: Apache-2.0 for `drizzle-orm`, MIT for `drizzle-kit`. Drizzle is still before 1.0, with 1.0 release candidates out, so this choice is emerging and reviewed every 90 days.

## What the team does

- Declare every table in the schema files that `drizzle.config.ts` names, and import the inferred row types from there.
- Add `drizzle-orm` and `drizzle-kit` as exact dependencies at the paired stable releases, and upgrade them together.
- Let the project's migration-tool standard plan the migrations, so the project has one planner. Under `typescript/atlas-migrations`, Atlas reads the tables through `drizzle-kit export`; never run `drizzle-kit generate` there. Only on D1, under `cloudflare/d1-migrations`, plan each migration on a laptop with `drizzle-kit generate`, answer its rename questions there, and commit the SQL with the `meta/` snapshots in the folder that `migrations_dir` names.
- Never run `drizzle-kit push` outside a scratch database.
- Write raw SQL through the `sql` template, so each value stays a bound parameter.

## What the gate runs

No `tests` entry of its own. The project's migration-tool standard runs the model drift check: `atlas migrate diff` under `typescript/atlas-migrations`, and `drizzle-kit generate` under `cloudflare/d1-migrations`. A schema change without its migration fails the change.
