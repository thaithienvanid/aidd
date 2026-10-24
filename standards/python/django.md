---
id: python/django
type: opinionated
fills: [apis-and-services:api-framework, schema-migration:orm, schema-migration:migration-tool]
default: false
implements: schema-migration:Model drift check
roles: [developer, architect, reviewer]
when_changed: ["**/*.py", "**/migrations/**", manage.py, pyproject.toml, openapi.yaml, schema.yml]
why: "Django comes with its ORM, migrations, admin, and auth in one framework, and Django REST framework adds the API layer, so one coherent option covers the API, the data mapping, and the migrations."
reviewed: "2026-10-16"
maturity: established
tool:
  name: django
  registry: pypi
  package: django
version_policy: current_stable
checked_version: "6.1.2"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://www.djangoproject.com/download/
evidence: The latest official version is 6.1.2.
alternatives: [FastAPI with SQLAlchemy and Alembic, Litestar, Flask]
status: active
enforced_by:
  - name: drift
    command: [uv, run, python, manage.py, makemigrations, --check, --noinput]
  - name: migrate
    command: [uv, run, python, manage.py, migrate, --noinput]
---

# Django and Django REST framework serve the Python API and own its data

It answers three choices as one option: api-framework of `aidd-team:apis-and-services`, and orm and migration-tool of `aidd-team:schema-migration`. aidd's defaults for Python are `python/fastapi-api`, `python/sqlalchemy-orm`, and `python/alembic-migrations`. This standard fills all three choices, so a project that adopts it adds none of those. Django and Django REST framework (DRF) are under the BSD 3-Clause license.

## What the team does

- Install a DRF release whose requirements list the Django series in use.
- Write the API with DRF serializers and viewsets, and validate each request body with a serializer.
- DRF's own OpenAPI generation is deprecated, and its docs recommend drf-spectacular. Generate the OpenAPI document with it, and commit the document as the contract.
- Write each schema change with `makemigrations`, and read the migration before you commit it.
- Give each `RunPython` operation a `reverse_code`, which Django calls to unapply the migration.
- Load relations on purpose, with `select_related` and `prefetch_related`.
- Run `manage.py check --deploy` against the production settings.

## What the gate runs

Two `tests` entries against a throwaway database, each with `--noinput`, so neither asks a question. `makemigrations --check` fails when a model changed without its migration; without `--noinput`, a renamed field would wait for an answer. `migrate` applies every migration.
