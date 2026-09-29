---
name: release-rollout
description: "Practice skill: ship a change progressively and be able to undo it. Use when planning or running a release or deploy, or when someone mentions shipping to production, a feature flag, a canary, blue-green, a staged or percentage rollout, rolling back, release notes, a changelog, a version bump, smoke tests in production, or a deploy that must not break users: feature flags, canary or blue-green rollout, rollback steps and triggers, migrations sequenced before code, read-only production smoke tests, versioning and release notes, and aidd observe during the window."
metadata:
  checked: "2026-09-28"
---

# Release and rollout

**Use it when** you plan or run a release, on the spec and emergency lanes.

**Do not use when** the change does not reach production on its own — a library, a Spec, or a docs change ships with whatever carries it; there is no rollout to plan.

## Standards

- Progressive delivery (feature flags, canary, blue-green) with automatic rollback.
- Trunk-based development.
- Semantic Versioning 2.0.0.
- Keep a Changelog 1.1.0.
- The five DORA software delivery metrics.

## Specify, before Spec approval

- The rollout plan, with the mechanism the project already has (a flag in code, a canary, blue-green; without one, a plain release with a tested rollback): stages, percentages, durations, and the metric that gates each stage; the rollback steps and the trigger, in the Spec's `rollback` and `[observe]`.
- Flags named, defaulting off, with a cleanup Task and a date; migrations sequenced so the expand step ships before the code that needs it.

## Implement

- Every deploy is backward compatible with the previous version, because two versions run during a rollout; schema changes are decoupled from deploys.
- Artifacts are versioned and immutable; release notes and the changelog are part of the change; secrets and configuration come from the environment.

## Test commands

- A deploy dry run; smoke tests against the deployed canary or release; synthetic checks on the critical path; a rollback rehearsal in a staging environment.
- Production smoke tests and synthetic checks are read-only; a check that must write (a sign-up, an order) writes only to a dedicated test tenant or account that reporting, billing, analytics, and customer messaging exclude, and cleans up after itself.
- A pre-production test run that cannot create its isolated database or environment fails the pipeline; it never falls back to a shared or production store.

## Ship

- Canary first where the project has one, then widen while the SLI holds; `aidd observe <spec> --write` at the start and the end of the window; a fired trigger means stop and say so, humans roll back within minutes, and the loop goes to Learn.
- Remove the flag within the promised number of releases; a flag left behind is a defect.

## Hand off

- Done: the rollout plan, the flag, and the release notes. Next: the SRE for the observe window, the author for the merge. Needs: an environment or a flag system the platform lacks. Stopped at: none, or the stop rule that fired.
