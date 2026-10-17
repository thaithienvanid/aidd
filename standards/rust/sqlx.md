---
id: rust/sqlx
type: opinionated
fills: [schema-migration:orm]
default: true
implements: schema-migration:Model drift check
roles: [developer, data-engineer, reviewer]
when_changed: ["**/*.rs", "**/*.sql", ".sqlx/**", "migrations/**", Cargo.toml, "**/Cargo.toml", Cargo.lock]
why: "SQLx checks plain SQL against the real schema at compile time, with no query DSL, and its offline metadata lets CI build without a database."
reviewed: "2026-10-16"
maturity: established
tool:
  name: sqlx
  registry: crates
  package: sqlx
version_policy: current_stable
checked_version: "0.9.0"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
pin: "0.9"
source: https://github.com/transact-rs/sqlx/blob/main/sqlx-cli/README.md
evidence: Exits with a nonzero exit status if the data in .sqlx is out of date with the current database schema or queries in the project.
alternatives: [Diesel, SeaORM, tokio-postgres with plain SQL]
status: active
enforced_by:
  - name: prepare
    command: [cargo, sqlx, prepare, --check, --workspace]
  - name: sqlx-major
    command: [cargo, tree, --locked, --invert, sqlx@0.9]
---

# SQLx maps the Rust code to the database

It answers the orm choice of `aidd-team:schema-migration`.

## What the team does

- Write queries with `sqlx::query!` and `sqlx::query_as!`, which the compiler checks against the schema.
- Commit the `.sqlx` folder that `cargo sqlx prepare --workspace` writes, and build in CI with `SQLX_OFFLINE=true`.
- Install `sqlx-cli` at the same version as the `sqlx` crate.
- For the prepare check, set `DATABASE_URL` to a throwaway database with every migration applied.

## What the gate runs

Two `tests` entries. `cargo sqlx prepare --check` fails when the committed query metadata no longer matches the schema or the queries. `cargo tree --invert` fails when `Cargo.lock` leaves the SQLx major this standard was checked at.
