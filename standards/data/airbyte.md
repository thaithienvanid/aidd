---
id: data/airbyte
type: opinionated
fills: [data-and-analytics:ingestion]
default: false
implements: data-and-analytics:Implement
roles: [architect, sre, reviewer]
when_changed: ["airbyte/**", "**/airbyte*.tf", "**/airbyte/**/*.yaml"]
why: "Airbyte runs ready-made connectors for hundreds of sources as a platform the team operates, for a team that needs many sources without writing a loader for each."
maturity: established
tool:
  name: abctl
  registry: github
  package: airbytehq/abctl
version_policy: current_stable
checked_version: "0.30.4"
checked: "2026-10-28"
checked_by: agent:claude-code/claude-opus-5-5
source: https://raw.githubusercontent.com/airbytehq/airbyte/master/README.md
evidence: Open-source data movement for ELT pipelines and AI agents
alternatives: [dlt, Fivetran]
status: active
---

# Airbyte moves data through its connectors

It answers the ingestion choice of `aidd-team:data-and-analytics` where the team runs a connector platform. Mind the license. Airbyte's platform is under the Elastic License 2.0: source-available, not open source, and never to be offered as a managed service. Its connectors are under the MIT license. Airbyte Cloud is its hosted product.

## What the team does

- For development or a small team, install it on a single machine with an exact `abctl` release. For production, install it on Kubernetes with Airbyte's Helm chart. Keep each connection's configuration in the repository (the Terraform provider or exported configuration), never only in the UI.
- Pin each connector's version, and upgrade one at a time with a sync run against a test destination.
- Land raw data in its own schema, and let the transformation models read it. A connector change then never reaches a published model directly.
