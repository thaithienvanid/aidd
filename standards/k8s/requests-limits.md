---
id: k8s/requests-limits
type: opinionated
fills: [cloud-and-infrastructure:spend-caps]
default: true
implements: cloud-and-infrastructure:Implement
roles: [sre, architect, reviewer]
when_changed: ["charts/**", "base/**", "overlays/**", "policy/kyverno/**"]
why: "A cluster's bill follows the nodes its pods ask for, so requests sized from a measured run, a quota on each namespace, and a cap on each autoscaler bound what a Kubernetes workload can cost."
reviewed: "2026-10-22"
maturity: established
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [a LimitRange default alone, alerts only]
status: active
source: https://kubernetes.io/docs/concepts/policy/resource-quotas/
evidence: A resource quota, defined by a ResourceQuota object, provides constraints that limit aggregate resource consumption per namespace.
---

# Requests, limits, and quotas cap what a Kubernetes workload costs

It answers the spend-caps choice of `aidd-team:cloud-and-infrastructure` on Kubernetes. Kubernetes is under the Apache License 2.0.

## What Kubernetes supports

As read on the `checked` day: the scheduler places a pod by its requests, and a container may use more than its request while the node has spare capacity. A ResourceQuota caps the total that one namespace can request.

## What the team does

- Give every container a CPU request and a memory request, sized from a measured run.
- Set each memory limit equal to its memory request. Set a CPU limit only for a reason the Spec names, because it throttles the container even while the node has spare CPU.
- Give each namespace a ResourceQuota on requests, limits, pods, and load balancers, and a LimitRange with defaults for a container that sets none.
- Give each HorizontalPodAutoscaler a `maxReplicas` that the quota can hold.
- Cap the node autoscaler at what the budget allows: the cluster autoscaler's maximum node count, or the `limits` of a Karpenter NodePool.
- Add a Kyverno rule to `policy/kyverno/` that requires CPU and memory requests and a memory limit on every container.

## What the gate runs

Nothing of its own. The rule runs in the `tests` entry of `k8s/pod-security-kyverno`, so a container with no requests or no memory limit fails the change.
