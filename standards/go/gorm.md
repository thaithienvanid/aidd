---
id: go/gorm
type: opinionated
fills: [schema-migration:orm]
default: false
implements: schema-migration:Model drift check
roles: [developer, data-engineer, reviewer]
when_changed: ["**/*.go", go.mod, go.sum, "migrations/**"]
why: "GORM is a full ORM for Go, with associations, hooks, preloading, and transactions, so a team that wants a model layer writes little SQL by hand."
reviewed: "2026-10-16"
maturity: established
tool:
  name: gorm
  registry: go
  package: gorm.io/gorm
version_policy: current_stable
checked_version: v1.31.2
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://proxy.golang.org/gorm.io/gorm/@latest
evidence: "\"Version\":\"v1.31.2\""
alternatives: [sqlc, Ent, pgx with plain SQL]
status: active
enforced_by:
  - name: drift
    command:
      - sh
      - -c
      - "out=$(go test -count=1 -v -run '^TestModelsMatchSchema$' ./... 2>&1); s=$?; printf '%s\\n' \"$out\"; test \"$s\" -eq 0 && printf '%s\\n' \"$out\" | grep -q -- '--- PASS: TestModelsMatchSchema'"
---

# GORM maps the Go code to the database

It answers the orm choice of `aidd-team:schema-migration`. aidd's default for Go is `go/sqlc`. This option is for a team that wants a full ORM in place of SQL it writes. GORM is under the MIT license.

## What the team does

- Write each schema change as a versioned migration with the project's migration tool, never with `AutoMigrate`. `AutoMigrate` adds tables, columns, and indexes, but it never drops an unused column, and it keeps no history.
- Pass each value from a caller as a `?` argument, such as `db.Where("name = ?", v)`. GORM's security guide shows that a condition built with `fmt.Sprintf` is open to SQL injection.
- Pass the request's context with `db.WithContext(ctx)`, so a cancelled request stops its query.
- Load associations on purpose with `Preload` or `Joins`. A query inside a loop is a review finding.
- Keep one `TestModelsMatchSchema` test. It applies every migration to the throwaway database that `DATABASE_URL` names, then checks each field of each model with `db.Migrator().HasColumn`.

## What the gate runs

One `tests` entry runs `TestModelsMatchSchema`. A model field with no column in the migrated schema fails the change. `go test` exits 0 with "no tests to run" when no test matches, so the check also needs the line `--- PASS: TestModelsMatchSchema`; a missing test fails the change.
