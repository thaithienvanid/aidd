+++
id = "python/alembic-migrations"
type = "opinionated"
fills = ["schema-migration:migration-tool"]
default = true
implements = "schema-migration:Migration up and down"
roles = ["developer", "data-engineer", "platform-engineer", "reviewer"]
when_changed = ["alembic/**", "migrations/**", "alembic.ini", "**/models.py", "**/models/**"]
why = "Alembic writes versioned migration scripts from the SQLAlchemy models, each with an upgrade and a downgrade, and runs them in one ordered history."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "alembic", registry = "pypi", package = "alembic" }
version_policy = "current_stable"
checked_version = "1.20.0"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
source = "https://pypi.org/pypi/alembic/json"
evidence = '"version":"1.20.0"'
alternatives = ["Atlas", "Flyway", "Liquibase"]
status = "active"
enforced_by = [
  { name = "upgrade", command = ["uv", "run", "alembic", "upgrade", "head"] },
  { name = "downgrade", command = ["uv", "run", "alembic", "downgrade", "-1"] },
  { name = "reupgrade", command = ["uv", "run", "alembic", "upgrade", "head"] },
]
+++

# Alembic writes and applies the Python migrations

It answers the migration-tool choice of `aidd-team:schema-migration`.

## What the team does

- Generate each migration with `alembic revision --autogenerate`, then read it and fix what autogenerate cannot see, such as a renamed column.
- Write a real `downgrade()` for every revision. One that cannot undo its change raises an error that says so, and the Spec names the way back.
- Read the database URL from the environment in `env.py`, never from `alembic.ini`.
- Plan a destructive change as `Expand and contract (parallel change) for data and APIs` of `aidd-team:schema-migration` says.
- After a merge of two branches, join their heads with `alembic merge` before the next migration.

## What the gate runs

Three `[[tests]]` entries against a throwaway database: upgrade to head, downgrade one revision, and upgrade again. A migration that fails either way fails the change.
