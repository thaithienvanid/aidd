---
id: tooling/flagd
type: opinionated
fills: [release-rollout:flag-provider]
default: true
implements: release-rollout:Feature flags
roles: [architect, developer, sre, reviewer]
when_changed: ["flags/**", "**/*.flagd.json", "**/flagd/**"]
why: "flagd evaluates OpenFeature flags from a JSON flag file in the repository, so every flip leaves a history, and each language reads it through its OpenFeature provider. It belongs to OpenFeature, a CNCF incubating project, under Apache-2.0."
maturity: emerging
tool:
  name: flagd
  registry: go
  package: github.com/open-feature/flagd/flagd
version_policy: current_stable
checked_version: "v0.18.2"
checked: "2026-11-04"
checked_by: agent:claude-code/claude-opus-5-5
source: https://raw.githubusercontent.com/open-feature/flagd/main/README.md
evidence: "a ready-made, open source, OpenFeature-compliant feature flag backend system"
alternatives: [an OpenFeature in-process provider, Unleash, GrowthBook, Flagsmith, LaunchDarkly]
status: active
---

# flagd serves the feature flags from a file in the repository

It answers the flag-provider choice of `aidd-team:release-rollout` once flags need a service of their own, the second rung of its provider ladder. flagd is under the Apache-2.0 license and lives in the OpenFeature project, which the CNCF moved to incubating on November 21, 2023. It has no 1.0 release yet, so it is marked emerging.

## What the team does

- Keep the flags in one `*.flagd.json` file in the repository, and start flagd on it with `--uri file:`, from its container image pinned by digest.
- Read each flag through the OpenFeature SDK and the flagd provider for the language. The code never calls flagd's HTTP or gRPC API itself.
- On Kubernetes, run flagd beside each app through the OpenFeature Operator.
- Keep the flag keys when the project later moves to a database or a vendor's provider, so only the provider setup changes.
