---
id: data/airflow
type: opinionated
fills: [data-and-analytics:orchestrator]
default: true
implements: data-and-analytics:Implement
roles: [architect, developer, sre, reviewer]
when_changed: ["dags/**", airflow.cfg]
why: "Apache Airflow schedules and runs the pipelines as code in the repository, with retries, backfills, and a record of every run, and it is the orchestrator most data teams already know."
reviewed: "2026-10-28"
maturity: established
tool:
  name: apache-airflow
  registry: pypi
  package: apache-airflow
version_policy: current_stable
checked_version: "3.3.2"
checked: "2026-10-28"
checked_by: agent:claude-code/claude-opus-5-5
pin: "3.3.2"
source: https://airflow.apache.org/docs/apache-airflow/stable/index.html
evidence: is an open-source platform for developing, scheduling, and monitoring workflows
alternatives: [Dagster, Prefect, the warehouse's or cloud's own scheduler]
status: active
enforced_by:
  - name: dag-import
    command: [python, -m, pytest, tests/dags]
---

# Apache Airflow runs the pipelines

It answers the orchestrator choice of `aidd-team:data-and-analytics`. Airflow is under the Apache License 2.0. Install it with the constraints file the project publishes for the Python version, as its docs ask, so its dependencies resolve the same everywhere.

## What the team does

- Keep each DAG small: it orders tasks, and the work runs in the tasks (a dbt build, a dlt pipeline), never at import time.
- Test that every DAG imports without errors and has no cycles, in CI, as `tests/dags` does; a DAG that fails to import never runs at all.
- Make every task safe to run twice. It writes by its logical date and overwrites its own partition, so a retry never duplicates data.
- Keep connections and secrets in a secrets backend, never in the DAG file.
