---
id: python/sqlalchemy-orm
type: opinionated
fills: [schema-migration:orm]
default: true
implements: schema-migration:Model drift check
roles: [developer, reviewer]
when_changed: ["**/models.py", "**/models/**", "alembic/**", alembic.ini, pyproject.toml]
why: "SQLAlchemy maps typed Python classes to tables and builds SQL with bound parameters, and Alembic's autogenerate compares those models with the migrated schema."
reviewed: "2026-10-16"
maturity: established
tool:
  name: sqlalchemy
  registry: pypi
  package: sqlalchemy
version_policy: current_major
checked_version: "2.1.6"
cooldown_until: "2026-10-28"
checked: "2026-10-24"
checked_by: agent:claude-code/claude-opus-5-5
source: https://pypi.org/pypi/sqlalchemy/json
evidence: "\"version\":\"2.1.6\""
alternatives: [SQLModel, Django ORM, plain SQL with psycopg]
status: active
enforced_by:
  - name: drift
    command: [uv, run, alembic, check]
---

# SQLAlchemy maps the Python code to the database

It answers the orm choice of `aidd-team:schema-migration`.

## What the team does

- Declare models with `DeclarativeBase` and `Mapped[...]` annotations, so the type checker sees each column's type and nullability.
- Give every model one shared `MetaData` with a naming convention for keys, indexes, and constraints, so migrations name them the same everywhere.
- Open one session per request or job, and commit or roll back in one place.
- Load relationships on purpose (`selectinload`, `joinedload`); lazy loading in a loop is a review finding.
- Build queries with `select()`; pass each value as a bound parameter, never through string formatting.

## What the gate runs

One `tests` entry runs `alembic check`, which fails when the models hold a change that no migration has. It needs the migration-tool standard's Alembic setup and a database at the head revision.
