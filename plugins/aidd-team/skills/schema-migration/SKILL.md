---
name: schema-migration
description: "Practice skill: change a schema, data contract, or pipeline safely. Use in an aidd repository when a Task adds a migration, column, index, event schema, or backfill."
metadata:
  checked: "2026-10-22"
---

# Schema migration

**Use it when** a Task adds a migration, column, index, table, event schema, or backfill. The `aidd-team:data-and-analytics` pack says what applies. This skill is how to do the work. It owns the migration plan, the backfill, and the rollback.

**Do not use when** no stored record, table, column, or serialized artifact changes shape. A rename inside one module is a refactor, and a migration for it invites a dual-write nobody needs.

## Standards

<!-- aidd:gen practice:schema-migration -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| Expand and contract (parallel change) for data and APIs | — | 2026-10-16 (reviewed) | <https://martinfowler.com/bliki/ParallelChange.html> |
| Reversible migrations, tested up and down on production-shaped data | — | 2026-10-16 (reviewed) | — |
| Migration tool conventions: versioned and repeatable scripts, checksum validation, no out-of-order apply in production, and a tested down path | — | 2026-10-16 (reviewed) | <https://documentation.red-gate.com/flyway> |
| Open Data Contract Standard (ODCS) (emerging) | v3.2.0 | 2026-10-16 | <https://github.com/bitol-io/open-data-contract-standard/releases> |
| GDPR Art. 5 and 17 for retention and deletion | Regulation (EU) 2016/679 | 2026-10-16 | <https://eur-lex.europa.eu/eli/reg/2016/679/oj> |
| Open table format for lakehouse tables: schema evolution, hidden partitioning, snapshots and time travel, with compaction and vacuum owned by the pipeline | Iceberg table spec v3; Iceberg 1.12.0 | 2026-10-16 | <https://iceberg.apache.org/spec/> |
| Data observability in the pipeline: freshness, volume, schema-drift, and column-level quality monitors that fail the run rather than fill a dashboard | — | 2026-10-16 (reviewed) | <https://greatexpectations.io/> |
| Idempotent, restartable pipelines with exactly-once or at-least-once stated | — | 2026-10-16 (reviewed) | — |

### Open choices

The team decides these. aidd's default holds until a `standards` entry fills one (`aidd standard list`).

| Choice | Question | aidd's default | Options |
| --- | --- | --- | --- |
| `orm` | Which library maps the code to the database? | The data-access library the project already uses. For a new project, the ecosystem's common one that checks its models against the schema. | SQLAlchemy, Drizzle, Prisma, Entity Framework Core, Hibernate (JPA), sqlc, sqlx, plain SQL |
| `migration-tool` | Which tool writes and applies the migrations? | The migration tool of the data-access library, with versioned scripts, checksums, and a down path. | Alembic, Flyway, Liquibase, Atlas, Prisma Migrate, drizzle-kit, EF Core migrations, golang-migrate |
<!-- aidd:end -->

## Specify

- Split the change into expand, migrate, and contract Tasks, each its own deploy. The destructive step never ships with the additive one.
- Update the data contract first, and list it in `design.files`. Name every producer and consumer.
- Plan the backfill: batch size, idempotency, resumability, and duration at the production row count.
- Write the rollback: the down migration, and what happens to rows written meanwhile.
- Name lock behavior: concurrent index builds, no rewrite of a large table, statement and lock timeouts. A large table changes online through a tool such as gh-ost for MySQL, or pgroll for Postgres, which serves both schemas at once. A lakehouse table uses its format's own schema evolution.
- Retention and deletion rules for personal data still hold after the change.

## Implement

- Additive first: a nullable column or a default the backfill computes, then `NOT NULL` once every row has a value.
- Dual-write or dual-read behind a flag while both shapes exist. Consumers read the contract, never the table.
- Batches log progress and can restart. Fixtures and logs hold no personal data.
- One migration history: after merging from the main branch, the tool shows no fork. Lock timeouts, backfill pauses, the evidence before a contract step, and each tool's history check: [references/safe-steps.md](references/safe-steps.md).
- Types, models, and client code mirroring a schema or data contract are generated from it, never copied by hand. Consumers vendor a producer's event schema at a pinned version.

## Review

- Every step reverses on its own. Lock time is bounded. The expand step leaves consumers unaffected. Retention and deletion rules still hold.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Migration up and down | the migration and its rollback run on a production-shaped snapshot | the repository's migration tool, up, down, then up again, timed, with row counts, null rates, and freshness before and after |
| Migration lint | no DDL that takes a long lock or rewrites a large table | `squawk` (v2.70.0) for Postgres, or the stack's DDL safety lint |
| Previous version on the new schema | the code still in production works on the expanded schema during a rolling deploy | the previous release's integration suite, run against the migrated database |
| Backfill run twice | the backfill is idempotent and resumable | run it twice, and stop and restart it once; row counts and checksums give the same result |
| Single migration head | parallel branches did not fork the migration history | the tool's history check in CI, from references/safe-steps.md |
| Model drift check | generated models and types match the schema; every declared column survives the mapping layer | regenerate, then `git diff --exit-code`; a field-survival test |

- From `aidd-team:data-and-analytics`: Contract validation, Data quality tests.

## Stop if

- The destructive step would ship in the same deploy as the additive one.
- The down migration has not run on production-shaped data.
- The migration history forked after merging from the main branch.

## Hand off

- Done: the migration files, the contract, and the backfill job. Next: the reviewer, and the SRE for the observe window (row counts, freshness). Needs: a production-shaped snapshot, if none exists. Stopped at: none, or the stop rule that fired.
