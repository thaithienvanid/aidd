---
id: k8s/helm-charts
type: opinionated
fills: [release-rollout:deploy-packaging]
default: true
implements: cloud-and-infrastructure:Manifest lint
roles: [sre, developer, reviewer]
when_changed: ["charts/**"]
why: "Helm packages a service's Kubernetes manifests as one versioned chart. With a values file for each environment, CI renders the same manifests the cluster receives, and a failed release rolls back to the last good one."
reviewed: "2026-10-22"
maturity: established
tool:
  name: helm
  registry: github
  package: helm/helm
version_policy: current_stable
checked_version: "4.3.1"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "4.3.1"
source: https://helm.sh/docs/helm/helm_lint/
evidence: This command takes a path to a chart and runs a series of tests to verify that the chart is well-formed.
alternatives: [Kustomize overlays, plain manifests]
status: active
enforced_by:
  - name: lint
    command: [sh, -c, "set -eu; for c in charts/*/; do helm lint --strict \"$c\"; done"]
  - name: render
    command:
      - sh
      - -c
      - "set -eu; rm -rf build/manifests; mkdir -p build/manifests; for c in charts/*/; do n=$(basename \"$c\"); for v in \"$c\"values-*.yaml; do e=$(basename \"$v\" .yaml); helm template \"$n\" \"$c\" -f \"$v\" > \"build/manifests/$n-${e#values-}.yaml\"; done; done"
---

# Helm 4 charts package the Kubernetes manifests

It answers the deploy-packaging choice of `aidd-team:release-rollout`. Helm is under the Apache License 2.0.

## What the team does

- Keep one chart for each service in `charts/<service>/`, with a `values-<environment>.yaml` beside the chart's own `values.yaml`.
- Install Helm at `pin` in CI, and write `apiVersion: v2` in each `Chart.yaml`.
- Pin each dependency chart to an exact version, and commit `Chart.lock`.
- Pin each image by its digest in the values, never by a tag that moves.
- Keep secrets out of the values. Reference a Secret that the cluster's secret store fills.
- Deploy with `helm upgrade --install --rollback-on-failure`, so a release that fails rolls back on its own.
- Render each environment in CI, so `k8s/kubeconform` and `k8s/pod-security-kyverno` check the files the cluster gets.

## What the gate runs

Two `tests` entries. `lint` runs `helm lint --strict` on each chart. `render` writes each chart for each environment to `build/manifests/` with `helm template`. A lint finding or a render error fails the change.
