---
name: schema-migration
description: "Practice skill: change a database schema, a data contract, or a pipeline safely. Use when a Task adds a migration, a column, an index, a table, an event schema, a data contract, or a backfill, or when someone says rename a column, change a type, drop a table, the migration locks the table, multiple migration heads, models out of sync with the database, or zero downtime: expand and contract, reversible steps, a single migration head, generated types with a drift check, zero downtime, and the test commands that prove them."
metadata:
  checked: "2026-09-28"
---

# Schema migration

**Use it when** a Task adds a migration, a column, an index, a table, an event schema, or a backfill. The `aidd-team:data-and-analytics` pack says what applies; this skill is how to do the work.

**Do not use when** no stored record, table, column, or serialized artifact changes shape; a rename inside one module is a refactor, and calling it a migration invites a dual-write nobody needs.

## Standards

- Expand and contract (parallel change).
- Reversible migrations.
- The Open Data Contract Standard v3.2.
- ISO/IEC 25012 data quality.
- GDPR Articles 5 and 17 for retention and deletion.

## Specify, before Spec approval

- Split the change into expand, migrate, and contract Tasks, each its own deploy; the destructive step never ships with the additive one.
- Update the data contract first and list it in `design.files`; name every producer and consumer.
- Plan the backfill: batch size, idempotency, resumability, expected duration on the production row count.
- Write the rollback: the down migration, and what happens to rows written in between.
- Name lock behavior: concurrent index builds, no table rewrites on large tables, statement timeouts.

## Implement

- Additive first: nullable column or a default computed by the backfill, then `NOT NULL` once every row has a value.
- Dual-write or dual-read behind a flag while both shapes exist; consumers read the contract, never the table.
- Batches log progress and can restart; no personal data in fixtures or logs.
- One migration head: after merging from the main branch, the migration tool's heads command prints one line (`alembic heads`, `prisma migrate status`, `rails db:migrate:status`, `flyway info`); two heads mean two branches wrote migrations in parallel, and a merge migration or a renumber comes before anything else.
- Types, models, and client code that mirror a schema or data contract are generated from it, never copied by hand; a producer's event schema is vendored by consumers at a pinned version.

## Test commands

- The migration up and down on a production-shaped snapshot, timed; row counts, null rates, and freshness before and after.
- Data quality tests (Great Expectations, dbt tests, or Soda); contract tests (datacontract-cli, emerging); a DDL safety lint such as squawk for Postgres.
- A single-head check in CI: the heads command's output has exactly one line.
- A drift check: regenerate the models or types from the schema, then `git diff --exit-code`; and a test that every column or field the contract declares survives the mapping layer, so a new one is not dropped silently.

## Review

- Every step is reversible on its own; lock time is bounded; consumers are unaffected by the expand step; retention and deletion rules still hold.

## Hand off

- Done: the migration files, the contract, and the backfill job. Next: the reviewer, and the SRE for the observe window (row counts, freshness). Needs: a production-shaped snapshot if none exists. Stopped at: none, or the stop rule that fired.
