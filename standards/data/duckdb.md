---
id: data/duckdb
type: opinionated
fills: [data-and-analytics:warehouse]
default: true
implements: data-and-analytics:Data quality tests
roles: [architect, developer, verifier, reviewer]
when_changed: ["models/**", "macros/**", "seeds/**", "snapshots/**", "tests/**/*.sql", dbt_project.yml, "profiles.yml"]
why: "DuckDB runs analytical SQL inside the process that calls it, with no server to install or run, so the models and their data tests run on one machine and in CI. It is under the MIT license, held by the DuckDB Foundation."
maturity: emerging
tool:
  name: duckdb
  registry: pypi
  package: duckdb
version_policy: current_stable
checked_version: "2.0.0"
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
source: https://duckdb.org/why_duckdb
evidence: "For DuckDB, there is no DBMS server software to install, update, and maintain."
alternatives: ["the team's warehouse", "SQLite, for row-by-row work rather than analytics"]
status: active
---

# DuckDB runs the models when the data fits one machine

It answers the warehouse choice of `aidd-team:data-and-analytics` when the data fits one machine, or when CI must run the models with no server. DuckDB 2.0 is a new major, so it is marked emerging. Past one machine, the team's own warehouse takes over.

## What the team does

- Pin `duckdb` and, with dbt, the `dbt-duckdb` adapter in the lockfile, each exactly.
- Keep the database file out of git. Point the `ci` target of `profiles.yml` at a file in the run's temporary folder, or at `:memory:`, so every run starts empty.
- Load the sources CI needs from small fixture files in the repository, never from production data.
- Write SQL that the production warehouse also runs, when DuckDB stands in for it in CI. Run the same models on the warehouse before release, because the two dialects differ.
- Move to the team's warehouse when several writers need the same data at once. DuckDB lets one process write to a database file at a time.

## What the tests run

It adds no command of its own. The `build` entry of `data/dbt-core` runs `dbt build --fail-fast` on the profile's target, so let CI pick DuckDB. Write `target: "{{ env_var('DBT_TARGET', 'dev') }}"` in `profiles.yml`, and set `DBT_TARGET=ci` in the CI job. That one run builds every model on DuckDB and runs its data tests.
