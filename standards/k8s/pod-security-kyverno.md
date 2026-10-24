---
id: k8s/pod-security-kyverno
type: opinionated
fills: [cloud-and-infrastructure:policy-tool]
default: true
implements: cloud-and-infrastructure:Policy as code
roles: [sre, security-engineer, reviewer]
when_changed: ["charts/**", "base/**", "overlays/**", "policy/kyverno/**"]
why: "Kyverno writes policies as Kubernetes resources, and its CLI runs in CI the policies its admission controller enforces, so a pod that breaks the restricted Pod Security Standard fails before it ships."
reviewed: "2026-10-22"
maturity: established
tool:
  name: kyverno
  registry: github
  package: kyverno/kyverno
version_policy: current_stable
checked_version: "1.19.2"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "1.19.2"
source: https://kyverno.io/docs/policy-types/cluster-policy/validate/
evidence: Starting in Kyverno 1.8, a new subrule type called podSecurity is available.
alternatives: [Pod Security Admission labels alone, Conftest (OPA) over the manifests]
status: active
enforced_by:
  - name: policies
    command: [kyverno, apply, policy/kyverno, --resource, build/manifests]
---

# Kyverno holds every workload to the restricted Pod Security Standard

It answers the policy-tool choice of `aidd-team:cloud-and-infrastructure` for Kubernetes manifests, beside `cost/policy-caps` for the IaC plan. Kyverno is under the Apache License 2.0.

## What the team does

- Commit the policies in `policy/kyverno/`. Start with one `ClusterPolicy` whose validate rule sets `podSecurity` to `level: restricted` and `version: latest`, with `failureAction: Enforce`.
- Label each application namespace `pod-security.kubernetes.io/enforce: restricted`, so the cluster's built-in Pod Security Admission still refuses a pod while Kyverno is down.
- Install Kyverno in the cluster from its Helm chart, at the release CI pins, with the same policies.
- Allow an exception only with a `PolicyException` for one named workload, written in the Spec, never with a lower level for a whole namespace.
- Install the Kyverno CLI at `pin` in CI.

## What the gate runs

One `tests` entry runs `kyverno apply policy/kyverno --resource build/manifests` on the manifests `k8s/helm-charts` or `k8s/kustomize` renders. A failed rule or an error exits 1 and fails the change.
