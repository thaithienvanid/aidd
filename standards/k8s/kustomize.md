---
id: k8s/kustomize
type: opinionated
fills: [release-rollout:deploy-packaging]
default: false
implements: cloud-and-infrastructure:Manifest lint
roles: [sre, developer, reviewer]
when_changed: ["base/**", "overlays/**"]
why: "Kustomize patches plain manifests for each environment with no template language, and kubectl reads its kustomization files, so a team that keeps plain YAML needs no chart."
reviewed: "2026-10-22"
maturity: established
tool:
  name: kustomize
  registry: github
  package: kubernetes-sigs/kustomize
version_policy: current_stable
checked_version: "5.8.3"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "5.8.3"
source: https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/
evidence: Kustomize is a standalone tool to customize Kubernetes objects through a kustomization file.
alternatives: [Helm charts, plain manifests]
status: active
enforced_by:
  - name: render
    command:
      - sh
      - -c
      - "set -eu; rm -rf build/manifests; mkdir -p build/manifests; for o in overlays/*/; do kustomize build \"$o\" > \"build/manifests/$(basename \"$o\").yaml\"; done"
---

# Kustomize overlays package the Kubernetes manifests

It answers the deploy-packaging choice of `aidd-team:release-rollout`. aidd's default is `k8s/helm-charts`. This option is for a team that keeps plain manifests and patches them for each environment. Kustomize is under the Apache License 2.0.

## What the team does

- Keep the shared manifests in `base/`, and one overlay for each environment in `overlays/<environment>/`.
- Install the standalone `kustomize` at `pin` in CI. The copy built into `kubectl` can be an older release.
- Change an environment with a patch in its overlay, never with a copy of the base.
- Set each image's digest with the overlay's `images` field.
- Pin each remote base to a tag or a commit, never to a branch.
- Build ConfigMaps with `configMapGenerator`, so a changed value rolls the pods.
- Render each overlay in CI, so `k8s/kubeconform` and `k8s/pod-security-kyverno` check the files the cluster gets.

## What the gate runs

One `tests` entry, `render`, writes each overlay to `build/manifests/` with `kustomize build`. A build error fails the change.
