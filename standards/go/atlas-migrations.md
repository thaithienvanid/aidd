---
id: go/atlas-migrations
type: opinionated
fills: [schema-migration:migration-tool]
default: true
implements: schema-migration:Migration up and down
roles: [developer, sre, reviewer]
when_changed: [atlas.hcl, "migrations/**", schema.sql, sqlc.yaml, sqlc.yml, sqlc.json]
why: "Atlas plans versioned SQL migrations from a desired schema, keeps a checksum of the history in atlas.sum, and computes the down step from the live database, and sqlc reads the same migrations folder."
reviewed: "2026-10-16"
maturity: emerging
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://atlasgo.io/community-edition
evidence: "The standard distribution is built from the same open-source codebase plus some additional proprietary features, and is free to download and use under the terms of the Atlas MSA."
pin: v1.3.4
alternatives: [goose, golang-migrate, Flyway]
status: active
enforced_by:
  - name: validate
    command: [atlas, migrate, validate, --env, local]
  - name: upgrade
    command: [atlas, migrate, apply, --env, ci]
  - name: downgrade
    command: [atlas, migrate, down, --env, ci, "1"]
  - name: reupgrade
    command: [atlas, migrate, apply, --env, ci]
---

# Atlas writes and applies the Go service's migrations

It answers the migration-tool choice of `aidd-team:schema-migration` for a Go service. The tool and its release feed are recorded once, in `typescript/atlas-migrations`; this file pins the same binary.

License: Ariga publishes the Atlas source under Apache-2.0, and its default binary under the Atlas MSA. The Community Edition build has no down, lint, or drift commands. The default binary at `pin` reverts a migration with no account; lint and drift detection are Atlas Pro features behind `atlas login`, which this file never uses.

## What the team does

- Install the default binary in CI and on each laptop with the official script at `pin`: `curl -sSf https://atlasgo.sh | ATLAS_VERSION=v1.3.4 sh`. Never build it from the Go module: a build from the GitHub repository is the Community Edition.
- Keep the desired schema in `schema.sql` and the history in `migrations/`. Plan each change with `atlas migrate diff`, review the SQL, and commit it with `atlas.sum`.
- Point the `schema` of `sqlc.yaml` at `migrations/`; sqlc parses Atlas's migration format.
- In `atlas.hcl`, the `local` env uses a disposable dev database; the `ci` env reads its target from `getenv("DATABASE_URL")`.
- Ship a destructive change as expand, migrate, and contract steps.

## What the gate runs

Four `tests` entries: the history is checked against `atlas.sum`; then, on a throwaway database, every migration is applied, the newest is reverted, and all are applied again. A failure at any step fails the change.
