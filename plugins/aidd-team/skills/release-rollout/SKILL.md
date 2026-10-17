---
name: release-rollout
description: "Practice skill: ship progressively and undo it. Use in an aidd repository for a release, a feature flag or kill switch, an A/B test, a canary, a staged rollout, or a rollback."
metadata:
  checked: "2026-09-30"
---

# Release and rollout

**Use it when** you plan or run a release, ship behind a flag or add a kill switch, run an A/B test, or a flag's cleanup comes due, on the spec and emergency lanes.

**Do not use when** the change does not reach production on its own: a library, a Spec, or a docs change ships with whatever carries it.

## Standards

<!-- aidd:gen practice:release-rollout -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| Progressive delivery (canary, blue-green, feature flags) with automatic rollback, and trunk-based development with short-lived branches | — | 2026-10-16 (reviewed) | — |
| Trunk-based development: everyone commits to one trunk, short-lived branches under a day, incomplete work behind a flag, and a release cut from the trunk rather than a long-lived release branch | — | 2026-10-16 (reviewed) | <https://trunkbaseddevelopment.com/> |
| The OpenFeature specification: a vendor-agnostic flag evaluation API, with a provider per flag system and flagd as its evaluation engine | v0.9.0 | 2026-10-16 | <https://github.com/open-feature/spec/releases> |
| Semantic Versioning | 2.0.0 | 2026-10-16 | <https://semver.org/> |
| Keep a Changelog | 1.1.0 | 2026-10-16 | <https://keepachangelog.com/en/1.1.0/> |
| DORA software delivery performance metrics: change lead time, deployment frequency, failed deployment recovery time, change fail rate, and deployment rework rate | five-metric model | 2026-10-16 | <https://dora.dev/guides/dora-metrics-four-keys/> |
| A tracking plan for product analytics events | — | 2026-10-16 (reviewed) | — |
| Controlled experiments: a power and sample-size calculation, a sample-ratio-mismatch check, and sequential always-valid inference when a test is watched | — | 2026-10-16 (reviewed) | <https://experimentguide.com/> |
<!-- aidd:end -->

## Specify

- The rollout plan uses the project's mechanism (a flag, a canary, blue-green, or a plain release with a tested rollback). It gives stages, percentages, durations, and the metric that gates each. The rollback and its trigger go in the Spec's `rollback` and `observe`.
- Sequence migrations so the expand step ships before the code that needs it.

### Feature flags

A flag releases a normal or major user-facing change apart from its deploy, or is a kill switch; never one nobody will flip. One `flags` entry per flag, with a person as `owner`. Its fields, and the provider, the first rung the project already runs, from an OpenFeature in-process provider to flagd on a flag file: [references/flags-and-experiments.md](references/flags-and-experiments.md).

### Experiments

An A/B test is a flag with `purpose` experiment that decides the Spec's `hypothesis`, planned in the Spec's `experiment` block. Before launch, set:

- exactly one primary metric, the one the hypothesis names
- `guardrails` that stop the test when they worsen
- a `min_sample` per variant from a power calculation, or a `duration` in whole weeks
- the `decision` rule, written before anyone sees data

Check daily for a sample ratio mismatch: the assignment or the logging is broken, so stop and fix it; no result from it counts. Stop early only on a guardrail breach or the mismatch, never on a good primary metric.

## Implement

- Every deploy works beside the previous version during a rollout. Schema changes are decoupled from deploys.
- Artifacts are versioned and immutable. Release notes and changelog ship in the change.
- Flags: code against the OpenFeature API. The code falls back to the Spec's default when the provider fails (default off in code and in the flag system). A kill switch stays after launch. Flags are not authorization: a flag decides what a user sees, never what they may do.

## Ship

- Canary first where there is one, then widen while the SLI holds. Run `aidd observe <spec> --window --write` in the background. On a fired trigger, stop and say so. Humans roll back within minutes, and the loop goes to Learn.
- Mobile: the store's phased release (`aidd-team:mobile-apps`). A store binary cannot be recalled, so a server-side flag is the rollback.
- Agents never flip a production flag: a person does. Turning the flag off is the first rollback step. Cleanup is a follow-up Spec that lists the flag in `removes_flags`. A flag left behind is a defect.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Deploy dry run | the deploy would apply cleanly | the deploy tool's dry-run mode |
| Canary smoke tests | the canary or release serves the critical path | read-only smoke tests; a write goes only to a test tenant that reporting, billing, and analytics exclude |
| Rollback rehearsal | the rollback works | in staging if there is one; else the runbook's rollback, rehearsed locally or in the observe window |
| Flag states | the Acceptance holds on, and the old behavior holds off | the suite in both states, each a `tests.commands` entry |
| Flag fallback | the code takes the default when the provider is unreachable | a test with the provider down |
| Isolated environment check | a pre-production run never falls back to a shared or production store | the pipeline fails when it cannot create its isolated environment |

## Stop if

- An agent would flip a production flag, or a flag has no person as owner.
- The rollout widens while the SLI or a guardrail is breached.
- An experiment shows a sample ratio mismatch, or someone wants to stop it early on a good number.

## Hand off

- Done: the rollout plan, the flag, and the release notes. Next: the SRE for the observe window, the author for the merge. Needs: an environment or a flag system the platform lacks. Stopped at: none, or the stop rule that fired.
