---
id: data/dbt-core
type: opinionated
fills: [data-and-analytics:transformation]
default: true
implements: data-and-analytics:Data quality tests
roles: [architect, developer, verifier, reviewer]
when_changed: ["models/**", "macros/**", "seeds/**", "snapshots/**", "tests/**/*.sql", dbt_project.yml, "profiles.yml", ".sqlfluff"]
why: "dbt Core keeps each warehouse model as a SELECT in the repository, with data tests and contracts beside it, so a change to a model is reviewed, tested, and built like code."
reviewed: "2026-10-28"
maturity: established
tool:
  name: dbt-core
  registry: pypi
  package: dbt-core
version_policy: current_stable
checked_version: "1.12.6"
checked: "2026-10-28"
checked_by: agent:claude-code/claude-opus-5-5
pin: "1.12.6"
source: https://docs.getdbt.com/docs/build/data-tests
evidence: Data tests are assertions you make about your models
alternatives: [SQLMesh, plain SQL files run by the orchestrator]
status: active
enforced_by:
  - name: build
    command: [dbt, build, --fail-fast]
  - name: sql-lint
    command: [sqlfluff, lint, models]
---

# dbt Core builds and tests the warehouse models

It answers the transformation choice of `aidd-team:data-and-analytics`. dbt Core is under the Apache License 2.0; dbt Cloud and the dbt Fusion engine are separate products with their own terms. SQLFluff (MIT), the SQL linter it pairs with, lints the models through its dbt templater, the `sqlfluff-templater-dbt` package.

## What the team does

- Pin `dbt-core`, its adapter (`dbt-postgres`, `dbt-snowflake`, and so on), SQLFluff, and `sqlfluff-templater-dbt` in the lockfile. Since dbt 1.8 an adapter is versioned on its own, so pin each one exactly.
- Give every model a test of its grain (`unique` and `not_null` on its key) and the relationships it promises. Put a contract (`contract: enforced`) on each model another team reads.
- Run `dbt build` in CI on the models a change touches and those downstream, against a disposable schema. Run `sqlfluff lint` on the SQL the change touches.
- Keep the profile's credentials out of the repository: `profiles.yml` reads them from the environment.
