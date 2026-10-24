---
id: postgres/managed-postgres
type: opinionated
fills: [cloud-and-infrastructure:database]
default: true
implements: cloud-and-infrastructure:Database connection pool
roles: [architect, developer, sre, reviewer]
when_changed: ["**/*.tf", "**/*.tofu", "migrations/**", "**/*.sql"]
why: "A managed PostgreSQL on a pinned major, with point-in-time recovery, a pooler, and a statement timeout, gives the application one well-known database whose restore, connections, and slowest query each have a bound."
reviewed: "2026-10-22"
maturity: established
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [MySQL (managed), a PostgreSQL the team runs itself on a VM or Kubernetes]
status: active
source: https://www.postgresql.org/support/versioning/
evidence: We recommend that users always run the current minor release associated with their major version.
---

# A managed PostgreSQL 18 holds the application's data

It answers the database choice of `aidd-team:cloud-and-infrastructure` on any host: Amazon RDS (`aws/rds-postgres`), Cloud SQL, Azure Database for PostgreSQL flexible server, Neon, or Supabase. PostgreSQL is under the PostgreSQL License.

## What PostgreSQL supports

As read on the `checked` day: PostgreSQL 18 is the newest supported major, first released in September 2025. PostgreSQL 19 is a release candidate. A managed service offers a new major some months after its release.

## What the team does

- Pin the major in the IaC, such as `engine_version = "18"`, and let the provider apply each minor release in a maintenance window.
- Move to a new major in a change of its own, after its tests pass against a restored copy of production.
- Turn on point-in-time recovery, with at least 7 days of retention and the RTO and RPO the Spec names. Restore into a scratch instance each quarter, and record the drill in the runbook.
- Put a pooler in front: the provider's own, or PgBouncer in transaction mode. Size the application's pool from the database's `max_connections`, never from a library default.
- Set `statement_timeout` and `idle_in_transaction_session_timeout` on the application's role (`ALTER ROLE app SET statement_timeout = '5s'`). Give only the migration role a longer one.
- Connect over TLS with `sslmode=verify-full`, with credentials from the secret store.
- On Supabase, each project gets a full PostgreSQL database. Turn on its point-in-time recovery add-on, which needs a paid plan ([database overview](https://supabase.com/docs/guides/database/overview)). Connect through its pooler in transaction mode, on port 6543 ([connection guide](https://supabase.com/docs/guides/database/connecting-to-postgres)).
- Give the application a role that owns no table, and the migrations a separate role that owns them.

## What the gate runs

Nothing of its own. The pack's Plan or dry-run check fails a plan that replaces the database without the Spec naming it.
