+++
id = "typescript/atlas-migrations"
type = "opinionated"
fills = ["schema-migration:migration-tool"]
default = true
implements = "schema-migration:Migration up and down"
roles = ["developer", "data-engineer", "platform-engineer", "reviewer"]
when_changed = ["atlas.hcl", "atlas/migrations/**", "prisma/schema.prisma", "prisma.config.ts", "**/schema.ts", "**/schema/**", "drizzle.config.ts", "package.json", "pnpm-workspace.yaml"]
why = "Atlas plans versioned SQL migrations from the ORM's schema through its official Prisma and Drizzle integrations, guards them with a checksum file, and computes a down migration against a dev database."
reviewed = "2026-10-09"
owner = "@thaithienvanid"
maturity = "emerging"
tool = { name = "atlas", registry = "npm", package = "@ariga/atlas" }
version_policy = "current_stable"
checked_version = "1.3.3"
checked = "2026-10-09"
checked_by = "agent:claude-code/claude-opus-5-5"
source = "https://registry.npmjs.org/-/package/@ariga/atlas/dist-tags"
evidence = '"latest":"1.3.3"'
pin = "1.3.3"
alternatives = ["Prisma Migrate (no down command)", "drizzle-kit migrate (no down path)", "Flyway"]
status = "active"
enforced_by = [
  { name = "validate", command = ["pnpm", "exec", "atlas", "migrate", "validate", "--env", "local"] },
  { name = "diff", command = ["pnpm", "exec", "atlas", "migrate", "diff", "--env", "local"] },
  { name = "drift", command = ["git", "diff", "--exit-code", "--", "atlas/migrations"] },
  { name = "upgrade", command = ["pnpm", "exec", "atlas", "migrate", "apply", "--env", "ci"] },
  { name = "downgrade", command = ["pnpm", "exec", "atlas", "migrate", "down", "--env", "ci", "1"] },
  { name = "reupgrade", command = ["pnpm", "exec", "atlas", "migrate", "apply", "--env", "ci"] },
]
+++

# Atlas writes and applies the TypeScript migrations

It answers the migration-tool choice of `aidd-team:schema-migration` for PostgreSQL, MySQL, MariaDB, or SQLite, under Prisma or Drizzle. For Cloudflare D1, which Atlas does not list, use `cloudflare/d1-migrations`.

Licence: the Atlas repository is Apache-2.0; `@ariga/atlas` installs the standard binary under Ariga's end-user licence (the Atlas MSA). The Apache-2.0 Community Edition has no `migrate down`, `migrate lint`, or schema drift detection. The standard binary runs `migrate down` without `atlas login`; `migrate lint` and drift detection need it and, after a 30-day trial, an Atlas Pro licence. This standard uses no Pro feature. `migrate lint` moved to Pro in v0.38, so it is reviewed every 90 days.

## What the team does

- Add `@ariga/atlas` as an exact dev dependency at `pin`. Its install script downloads the binary; pnpm 12 fails with `ERR_PNPM_IGNORED_BUILDS` until you commit `allowBuilds: {'@ariga/atlas': true}` in `pnpm-workspace.yaml`, which `pnpm approve-builds @ariga/atlas` writes.
- In `atlas.hcl`, read the ORM's schema through `data "external_schema"`, as Atlas's guides show: `prisma migrate diff --from-empty --to-schema prisma/schema.prisma --script`, or `drizzle-kit export`. Keep the migrations in `atlas/migrations`.
- Give the `local` and `ci` envs a throwaway `docker://` dev database; `ci` reads its target from `getenv("DATABASE_URL")`.
- Write each migration with `atlas migrate diff`, read it, and commit it with `atlas.sum`. Atlas is the only planner: never run `drizzle-kit generate` or `prisma migrate dev`.
- A destructive change follows `Expand and contract (parallel change) for data and APIs` of `aidd-team:schema-migration`.

## What the gate runs

Six `[[tests]]` entries, none of them interactive. `atlas migrate validate` checks the history against `atlas.sum`. In the model drift check, `atlas migrate diff` writes the migration a model change lacks, and `git diff --exit-code` fails on the changed `atlas.sum`. Then a throwaway database takes apply, one step down, and apply again. Any failure fails the change.
