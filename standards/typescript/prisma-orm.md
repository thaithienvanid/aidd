---
id: typescript/prisma-orm
type: opinionated
fills: [schema-migration:orm]
default: false
implements: schema-migration:Model drift check
roles: [developer, reviewer]
when_changed: ["prisma/**", prisma.config.ts, package.json]
why: "Prisma declares the data model in one schema file and generates a typed client from it, which suits a larger server team that wants the model reviewed in one place."
reviewed: "2026-10-16"
maturity: established
tool:
  name: prisma
  registry: npm
  package: prisma
version_policy: pinned
checked_version: "7.10.0"
checked: "2026-10-09"
checked_by: agent:claude-code/claude-opus-5-5
source: https://registry.npmjs.org/-/package/prisma/dist-tags
evidence: "\"prev\":\"7.10.0\",\"latest\":\"8.0.0-rc.22\""
pin: "7.10.0"
alternatives: [Drizzle, Kysely, TypeORM]
status: active
---

# Prisma maps the TypeScript server code to the database

It answers the orm choice of `aidd-team:schema-migration`, for a server on Node.js. License: Apache-2.0.

This file pins the Prisma ORM 7 line. On 2026-10-09 the npm `latest` tag of `prisma` is a Prisma ORM 8 release candidate, and `npm install prisma` gives the Prisma ORM 8 tool. Prisma ORM 8 has a schema format of its own, the contract. Since Prisma's changelog of 2026-10-02, it can also read the `schema.prisma` of a Prisma ORM 7 PostgreSQL project through `prisma orm init --from-prisma7-schema`, and some Prisma 7 features, such as views, are not supported yet. Prisma's release-status page expects Prisma ORM 8 in October 2026, with fixes for Prisma ORM 7 for 18 months after that. Check this choice again when Prisma ORM 8 is final.

## What the team does

- Add `prisma` and `@prisma/client` as exact dependencies on the 7 line, and upgrade them together. In a script or CI, call `prisma@7`, never a bare `npx prisma`.
- Keep the model in `prisma/schema.prisma` and the connection in `prisma.config.ts`, read from `DATABASE_URL`.
- Let the project's migration-tool standard write the migrations. Under `typescript/atlas-migrations`, Atlas reads the model through `prisma migrate diff --from-empty --to-schema prisma/schema.prisma --script`. Never run `prisma db push` or `prisma migrate dev` against a shared database.
- On an edge runtime, use an edge-compatible database driver with its Prisma driver adapter.
- Write raw SQL only through `$queryRaw` with a tagged template, so each value stays a bound parameter.

## What the gate runs

No `tests` entry of its own. The project's migration-tool standard runs the model drift check: under `typescript/atlas-migrations`, a model change without its migration fails the change.
