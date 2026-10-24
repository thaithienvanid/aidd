---
id: postgres/cross-schema-foreign-keys
type: opinionated
fills: [modular-monolith:module-boundaries]
default: true
implements: modular-monolith:Cross-schema foreign keys
roles: [architect, developer, reviewer]
when_changed: ["modules/*/migrations/**", "migrations/**", "**/*.sql"]
why: "A foreign key from one module's schema into another's ties their data together, and one query on the PostgreSQL catalog finds every such key after the migrations run."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://www.postgresql.org/docs/current/catalog-pg-constraint.html
evidence: f = foreign key constraint
alternatives: [a role for each module that can reach only its own schema]
status: active
enforced_by:
  - name: foreign-keys
    command:
      - sh
      - -c
      - "set -eu; out=$(psql -X -A -t -w -v ON_ERROR_STOP=1 -d \"${DATABASE_URL:?set DATABASE_URL to the migrated test database}\" -c \"SELECT c.conname, sn.nspname, st.relname, tn.nspname, tt.relname FROM pg_catalog.pg_constraint c JOIN pg_catalog.pg_class st ON st.oid = c.conrelid JOIN pg_catalog.pg_namespace sn ON sn.oid = st.relnamespace JOIN pg_catalog.pg_class tt ON tt.oid = c.confrelid JOIN pg_catalog.pg_namespace tn ON tn.oid = tt.relnamespace WHERE c.contype = 'f' AND sn.oid <> tn.oid\"); test -z \"$out\" || { printf 'foreign keys across schemas:\\n%s\\n' \"$out\"; exit 1; }"
---

# No foreign key crosses a module's PostgreSQL schema

It answers the module-boundaries choice of `aidd-team:modular-monolith` for the data of a PostgreSQL database, beside the import check of the code's ecosystem. PostgreSQL and `psql` are under the PostgreSQL License.

## What the team does

- Give each module its own schema, named after the module. Keep the module's tables there and nowhere else.
- Refer to a row of another module by its ID alone. Never add a foreign key to it.
- In CI, start a throwaway PostgreSQL, apply every module's migrations, and set `DATABASE_URL` to that database before the gate's tests run.
- Fix a reported key with a new migration that drops it. The check has no ignore list, so a known violation stays a waiver of the project rule until the migration ships.

## What the gate runs

One `tests` entry runs the query below with `psql`. It joins `pg_constraint` (`contype = 'f'`) to the schemas of both tables, and prints each key whose two schemas differ. Any row fails the change. A connection error also fails it, and `-w` makes `psql` fail rather than ask for a password.

```sql
SELECT c.conname, sn.nspname, st.relname, tn.nspname, tt.relname
FROM pg_catalog.pg_constraint c
JOIN pg_catalog.pg_class st ON st.oid = c.conrelid
JOIN pg_catalog.pg_namespace sn ON sn.oid = st.relnamespace
JOIN pg_catalog.pg_class tt ON tt.oid = c.confrelid
JOIN pg_catalog.pg_namespace tn ON tn.oid = tt.relnamespace
WHERE c.contype = 'f' AND sn.oid <> tn.oid;
```
