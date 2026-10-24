---
id: cloudflare/d1-table-prefixes
type: opinionated
fills: [modular-monolith:module-boundaries]
default: true
implements: modular-monolith:Data per module
roles: [architect, developer, reviewer]
when_changed: ["migrations/**", wrangler.jsonc, wrangler.json, wrangler.toml]
why: "D1 has no schemas and no roles, so a table prefix marks each module's tables, and one SQLite query over the applied migrations finds a foreign key between two prefixes or a table with none."
reviewed: "2026-10-16"
maturity: emerging
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://sqlite.org/pragma.html
evidence: The table-valued functions for PRAGMA feature was added in SQLite version 3.16.0 (2017-01-02).
alternatives: [one D1 database for each module]
status: active
enforced_by:
  - name: prefixes
    command:
      - sh
      - -c
      - "set -eu; dir=${D1_MIGRATIONS_DIR:-migrations}; db=$(mktemp); trap 'rm -f \"$db\"' EXIT; for f in \"$dir\"/*.sql; do [ -e \"$f\" ] || {echo \"no migrations in $dir\"; exit 1;}; sqlite3 -bail \"$db\" < \"$f\"; done; out=$(sqlite3 -bail \"$db\" \"SELECT m.name || ' -> ' || f.[table] FROM sqlite_master AS m, pragma_foreign_key_list(m.name) AS f WHERE m.type = 'table' AND m.name <> 'd1_migrations' AND substr(m.name, 1, 7) <> 'sqlite_' AND substr(m.name, 1, 4) <> '_cf_' AND lower(substr(m.name, 1, instr(m.name, '_') - 1)) <> lower(substr(f.[table], 1, instr(f.[table], '_') - 1)) UNION ALL SELECT name || ' has no module prefix' FROM sqlite_master WHERE type = 'table' AND instr(name, '_') < 2 AND substr(name, 1, 4) <> '_cf_'\"); test -z \"$out\" || {printf '%s\\n' \"$out\"; exit 1;}"
---

# Each module's D1 tables carry its prefix, and no foreign key crosses one

It answers the module-boundaries choice of `aidd-team:modular-monolith` for the data of a Cloudflare D1 database, beside `typescript/dependency-cruiser` for the code. SQLite is in the public domain.

## The risk

D1's SQL docs list `PRAGMA foreign_key_list("TABLE_NAME")`. They do not list the table-valued function `pragma_foreign_key_list()` that the query needs. So the check never runs on D1. It applies the migrations to a local SQLite file with the `sqlite3` shell, version 3.16.0 or later, and runs the query there.

## What the team does

- Name each table `<module>_<name>`, such as `orders_line_items`. The check reads the prefix up to the first `_`, so a prefix never contains `_`. Give a module of two words, such as `order-fulfillment`, a one-word prefix, and write it in the module's README.
- Store a reference to another module's row as a plain ID column, with no foreign key.
- Keep the migrations in `migrations/`, Wrangler's default `migrations_dir`. For another folder, the CI job sets `D1_MIGRATIONS_DIR`.
- Write migrations that plain SQLite also runs.

## What the gate runs

One `tests` entry applies every migration in name order to an empty SQLite file. A migration that fails stops the check. Then it prints each foreign key whose two tables have different prefixes, and each table with no prefix. Any row fails the change, and so does an empty migrations folder.
