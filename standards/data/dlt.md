---
id: data/dlt
type: opinionated
fills: [data-and-analytics:ingestion]
default: true
implements: data-and-analytics:Implement
roles: [architect, developer, reviewer]
when_changed: ["pipelines/**", ".dlt/config.toml"]
why: "dlt is a Python library that loads data from APIs, databases, and files into the warehouse, so each pipeline lives in the repository and is reviewed and tested like the rest of the code."
reviewed: "2026-10-28"
maturity: emerging
tool:
  name: dlt
  registry: pypi
  package: dlt
version_policy: current_stable
checked_version: "1.31.0"
checked: "2026-10-28"
checked_by: agent:claude-code/claude-opus-5-5
pin: "1.31.0"
source: https://dlthub.com/docs/intro
evidence: dlt is an open-source Python library that loads data from various, often messy data sources into well-structured datasets
alternatives: [Airbyte, Fivetran, hand-written loaders]
status: active
---

# dlt loads the sources into the warehouse

It answers the ingestion choice of `aidd-team:data-and-analytics`. dlt is under the Apache License 2.0; it is a library, not a service, so it runs inside the orchestrator's tasks. It is newer than Airbyte and Fivetran, so it is marked emerging. It is the default all the same, because the established options run outside the repository: Airbyte's platform is source-available and Fivetran is a hosted service.

## What the team does

- Write one pipeline per source, loading incrementally by a cursor (an `updated_at`, an id). Choose merge or append per table, so a rerun never duplicates rows.
- Keep credentials in `.dlt/secrets.toml` or the environment, never committed; commit `.dlt/config.toml` without secrets.
- Freeze the schema of a table another model reads (`schema_contract`). A source that adds or retypes a column then stops the load, never changing the model's input silently.
- Test a pipeline against DuckDB with recorded responses, so CI never calls the live source.
