---
name: ci-pipeline
description: "Practice skill: change CI, CD, or build pipelines safely. Use in an aidd repository when a Task touches a workflow, build script, Dockerfile, release job, or IaC, or CI is red."
metadata:
  checked: "2026-09-30"
---

# CI pipeline

**Use it when** a Task touches a workflow, a build script, a container image, or infrastructure as code. CI/CD files are protected paths (major, the security pool); IaC, containers, and Kubernetes manifests are baseline rules (normal) unless a dimension, a risk rule, or a protected path raises them. The `aidd-team:cloud-and-infrastructure` pack says what applies. This skill is how to do the work.

**Do not use when** the change touches no pipeline, build, or artifact. A test command in a Spec is the tester's, not a pipeline change.

## Standards

<!-- aidd:gen practice:ci-pipeline -->
| Standard | Edition |
| --- | --- |
| SLSA | v1.2, 2025 |
| SBOM in CycloneDX (with ML-BOM) or SPDX, and VEX | 1.7.2 |
| Least-privilege CI: OIDC federation over long-lived secrets, actions pinned by commit SHA | — |
| Reproducible builds: the same source, environment, and instructions give bit-for-bit identical artifacts | — |
| The Twelve-Factor App | — |
| CIS Benchmarks for images and clusters | — |

Each standard's checked date and source are in the aidd-team roles reference (`references/roles.md` in `aidd-team:aidd-team`), section `aidd-team:ci-pipeline`.
<!-- aidd:end -->

## Specify

- Say what runs where, with which permissions. A job running pull-request code never holds a secret. The plan or dry-run output is part of the Acceptance.
- Name the rollback: the previous workflow version, image digest, or state file.

## Implement

- Set `permissions:` per job to the minimum. Pin every action and image by SHA or digest, the version in a comment. `pull_request_target` never checks out pull-request code.
- Untrusted input (titles, bodies, branch names) reaches a `run:` step only through an environment variable, never `${{ }}` in the script.
- Key caches by lockfile. Jobs have timeouts and concurrency groups. Artifacts have retention. Builds are hermetic, reproducible, and attested (SLSA provenance, an SBOM).
- aidd's default target: the pull-request pipeline takes under 10 minutes at the 90th percentile; change it to fit. A slower one is a defect: fix it like a failing test, with caches and parallel jobs, never by skipping a check.
- Publishing to a package registry (trusted publishing, the Scorecard, the OSPS Baseline) is `aidd-team:package-publishing`'s.
- The `dev_basics` product default (formatter, linter, type check, pre-commit, update bot): `aidd-team:product-defaults`.

### Twelve-Factor

The Twelve-Factor App's build and deploy factors; the runtime ones are `aidd-team:observability`'s.

- **One codebase, many deploys.** One repository per deployable. Staging and production run the same code at different releases, never a fork per environment.
- **Dependencies declared and locked.** Every dependency is in the manifest and the lockfile. The build never relies on a tool that happens to be on the runner.
- **Separate build, release, run.** Build once into an immutable artifact (an image by digest). A release is that artifact plus one environment's config. Never rebuild per environment: promote the same digest. A rollback is the previous release.
- **Dev/prod parity.** Use the same kind of backing service in development, CI, and production (a Postgres container, not SQLite). Keep commit-to-deploy time short.

Test:

- The deployed digest equals the built one
- The image holds no environment file (`.env`, per-environment config)
- The integration job runs on the production backing service's type and major version

## Review

- Flag any elevated permission, unpinned reference, secret reachable from pull-request code, or drift between the plan and the Spec.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Workflow lint | no workflow syntax error, over-broad permission, or injectable expression | `actionlint` (v1.7.12) and `uvx zizmor==1.30.1 .` (zizmor emerging) |
| Shell syntax check | every shell script parses | `sh -n` on each script |
| Pipeline time | the pull-request pipeline stays under 10 minutes at the 90th percentile | the 90th percentile of wall time over the last 30 days of pull-request runs: `gh run list --event pull_request --status completed --limit 500 --json workflowName,headSha,startedAt,updatedAt`, or the platform's pipeline analytics. It measures each workflow run, so for a PR with several workflows take the longest one; `--limit` must cover the whole window |
| Build-once digest check | every job and deploy uses the one built digest; the image holds no environment file | a CI step that compares digests and lists the image's files |

- From `aidd-team:cloud-and-infrastructure`: IaC scanning, Plan or dry-run check.
- From `aidd-team:enterprise-controls`: Container scan and SBOM.

## Stop if

- A job that runs pull-request code would hold a secret, or `pull_request_target` would check it out.
- An action or image is referenced by a tag, not a SHA or digest.
- The plan destroys or replaces something the Spec did not name.

## Hand off

- Done: the pipeline change, its checks green, the plan attached. Next: the reviewer from the security pool. Needs: a secret, an environment, or a runner the platform team must create. Stopped at: none, or the stop rule that fired.
