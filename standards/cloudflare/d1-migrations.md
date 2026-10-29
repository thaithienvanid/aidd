---
id: cloudflare/d1-migrations
type: opinionated
fills: [schema-migration:migration-tool]
default: true
implements: schema-migration:Migration up and down
roles: [developer, sre, reviewer]
when_changed:
  - "migrations/**"
  - wrangler.jsonc
  - wrangler.json
  - wrangler.toml
  - "**/schema.ts"
  - "**/schema/**"
  - drizzle.config.ts
  - package.json
why: "Wrangler applies a D1 database's SQL migrations in order, records each one in the database, and skips its confirmation question in CI, so no second tool is needed for D1."
reviewed: "2026-10-16"
maturity: emerging
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://developers.cloudflare.com/d1/wrangler-commands/
evidence: "When running the apply command in a CI/CD environment or another non-interactive command line, the confirmation step will be skipped, but the backup will still be captured."
alternatives: [Atlas for PostgreSQL behind Hyperdrive (Atlas does not list D1)]
status: active
enforced_by:
  - name: drift
    command:
      - node
      - -e
      - "const fs = require('node:fs'); const p = fs.existsSync('package.json') ? JSON.parse(fs.readFileSync('package.json', 'utf8')) : {}; if (!{...p.dependencies, ...p.devDependencies}['drizzle-kit']) {console.log('package.json names no drizzle-kit: no ORM schema to compare.'); process.exit(0);} const r = require('node:child_process').spawnSync('pnpm', ['exec', 'drizzle-kit', 'generate'], {encoding: 'utf8'}); const out = String(r.stdout) + String(r.stderr); process.stdout.write(out); process.exit(r.status === 0 && out.includes('No schema changes') ? 0 : 1);"
  - name: apply
    command: [pnpm, exec, wrangler, d1, migrations, apply, DB, --local]
---

# Wrangler applies the D1 migrations

It answers the migration-tool choice of `aidd-team:schema-migration` for a Cloudflare D1 database. Wrangler is MIT or Apache-2.0, at the user's choice.

D1 migrations go forward only: Wrangler creates, lists, and applies them, and has no down command. A failed migration is rolled back on its own. To undo one that succeeded, write a new migration, or restore the database with Time Travel.

## What the team does

- Bind the database as `DB` in the Wrangler file, so the gate's command finds it.
- Add `wrangler` as an exact dev dependency, so `pnpm exec wrangler` runs the project's release.
- With `typescript/drizzle-orm`, plan the SQL with `drizzle-kit generate`, and point its `out` at the folder `migrations_dir` names. Without an ORM, start each file with `wrangler d1 migrations create`.
- Never edit a migration after it is applied anywhere; the `d1_migrations` table records it by name.
- Write each down plan in the Spec: the new forward migration, or the Time Travel bookmark to restore.

## What the gate runs

Two `tests` entries. The model drift check runs `drizzle-kit generate` when `package.json` names drizzle-kit, and passes only when it prints that there are no schema changes. Without a terminal, drizzle-kit 0.31 does not ask about a rename: it prints an error and still exits 0, so the check reads the output, not the exit code. Then every migration is applied to the local D1 database with `--local`, which starts empty on each CI run and asks no question there. A schema change without its migration, or a migration that fails, fails the change.
