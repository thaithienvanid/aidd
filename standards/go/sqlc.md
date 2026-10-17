---
id: go/sqlc
type: opinionated
fills: [schema-migration:orm]
default: true
implements: schema-migration:Model drift check
roles: [developer, data-engineer, reviewer]
when_changed: [sqlc.yaml, sqlc.yml, sqlc.json, "**/*.sql", "**/*.go"]
why: "sqlc compiles plain SQL against the schema and generates typed Go code for each query, so a query that no longer fits the schema fails before it runs."
reviewed: "2026-10-16"
maturity: established
tool:
  name: sqlc
  registry: go
  package: github.com/sqlc-dev/sqlc
version_policy: current_stable
checked_version: v1.31.1
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
pin: v1.31.1
source: https://docs.sqlc.dev/en/latest/
evidence: sqlc generates fully type-safe idiomatic Go code from SQL.
alternatives: [GORM, Ent, pgx with plain SQL]
status: active
enforced_by:
  - name: diff
    command: [go, run, github.com/sqlc-dev/sqlc/cmd/sqlc@v1.31.1, diff]
---

# sqlc maps the Go code to the database

It answers the orm choice of `aidd-team:schema-migration`.

## What the team does

- Keep `sqlc.yaml` at the root, and point its `schema` at the migrations folder, so the migrations stay the one source of the schema.
- Write each query in a `.sql` file under its `-- name: GetItem :one` annotation. Go code never builds SQL strings.
- For PostgreSQL, generate for the `pgx/v5` driver.
- Commit the generated code, and never edit it by hand.

## What the gate runs

One `tests` entry runs `sqlc diff` at `pin`. It generates the code in memory and fails when the committed code differs.
