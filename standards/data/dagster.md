---
id: data/dagster
type: opinionated
fills: [data-and-analytics:orchestrator]
default: false
implements: data-and-analytics:Implement
roles: [architect, developer, sre, reviewer]
when_changed: ["**/definitions.py", "**/assets/**", dagster.yaml, workspace.yaml]
why: "Dagster declares the data assets as Python functions with their lineage, and tests them like code, for a team that wants the pipeline's graph and its tests in the repository."
maturity: established
tool:
  name: dagster
  registry: pypi
  package: dagster
version_policy: current_stable
checked_version: "1.13.27"
checked: "2026-10-28"
checked_by: agent:claude-code/claude-opus-5-5
source: https://raw.githubusercontent.com/dagster-io/dagster/master/python_modules/dagster/README.md
evidence: Dagster is a cloud-native data pipeline orchestrator for the whole development lifecycle
alternatives: [Apache Airflow, Prefect]
status: active
enforced_by:
  - name: definitions
    command: [dagster, definitions, validate]
---

# Dagster declares the data assets

It answers the orchestrator choice of `aidd-team:data-and-analytics` when the team wants assets, not tasks. Dagster is under the Apache License 2.0; Dagster+ is its hosted product.

## What the team does

- Declare each table or model as an asset with the assets it reads, so the graph is the lineage. Load dbt models as assets, never as one `dbt build` step.
- Validate the definitions in CI (`dagster definitions validate`) and test each asset's function with plain inputs.
- Partition assets by date where the data arrives by date, so a backfill reruns one partition and never the whole history.
