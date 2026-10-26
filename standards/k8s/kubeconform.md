---
id: k8s/kubeconform
type: opinionated
fills: [ci-pipeline:manifest-validation]
default: true
implements: cloud-and-infrastructure:Manifest lint
roles: [sre, developer, reviewer]
when_changed: ["charts/**", "base/**", "overlays/**"]
why: "kubeconform checks each rendered manifest against the schemas of the cluster's Kubernetes version, with no cluster to reach, so an unknown field or a removed API fails in CI, not at deploy time."
reviewed: "2026-10-22"
maturity: established
tool:
  name: kubeconform
  registry: github
  package: yannh/kubeconform
version_policy: current_stable
checked_version: "0.8.0"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "0.8.0"
source: https://raw.githubusercontent.com/yannh/kubeconform/master/Readme.md
evidence: Kubeconform is a Kubernetes manifest validation tool.
alternatives: [a server-side dry run against a cluster]
status: active
enforced_by:
  - name: schemas
    command:
      - sh
      - -c
      - "kubeconform -strict -summary -kubernetes-version \"${KUBERNETES_VERSION:?set KUBERNETES_VERSION to the cluster version, such as 1.37.0}\" build/manifests"
---

# kubeconform checks the rendered manifests against the Kubernetes schemas

It answers the manifest-validation choice of `aidd-team:ci-pipeline`. kubeconform is under the Apache License 2.0.

## What kubeconform supports

As read on the `checked` day: it downloads the schemas for the Kubernetes version it is given from the kubernetes-json-schema project on GitHub. It fails a resource whose schema it cannot find, unless it is told to skip one.

## What the team does

- Set `KUBERNETES_VERSION` in CI to the version the production cluster runs, and move it in the change that upgrades the cluster.
- Install kubeconform at `pin` in CI, and keep the downloaded schemas with `-cache`.
- Commit the JSON schema of each custom resource the manifests use. Add `-schema-location default` and a `-schema-location` for that folder to the test.
- Never add `-ignore-missing-schemas`, so a misspelled kind fails rather than passes.

## What the gate runs

One `tests` entry runs `kubeconform -strict -summary` over `build/manifests/`, which `k8s/helm-charts` or `k8s/kustomize` renders. An invalid resource, a field the schema lacks, a missing schema, or an unset `KUBERNETES_VERSION` fails the change.
