---
name: ci-pipeline
description: "Practice skill: change CI, CD, or build pipelines safely. Use in an aidd repository when a Task touches a workflow, build script, Dockerfile, release job, or IaC, or CI is red."
metadata:
  checked: "2026-10-22"
---

# CI pipeline

**Use it when** a Task touches a workflow, a build script, a container image, or infrastructure as code. The gate sets the route from the paths, and `aidd-team:cloud-and-infrastructure` says which route applies. The `aidd-team:cloud-and-infrastructure` pack says what applies, and this skill is how to do the work.

**Do not use when** the change touches no pipeline, build, or artifact. A test command in a Spec is the verifier's, not a pipeline change.

## Standards

<!-- aidd:gen practice:ci-pipeline -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| SLSA | v1.2, 2025 | 2026-10-16 | <https://slsa.dev/> |
| SBOM in CycloneDX (with ML-BOM) or SPDX, and VEX | 1.7.2 | 2026-10-16 | <https://github.com/CycloneDX/specification/releases/tag/1.7.2> |
| Least-privilege CI: OIDC federation over long-lived secrets, actions pinned by commit SHA | — | 2026-10-16 | <https://docs.github.com/en/actions/concepts/security/openid-connect> |
| Reproducible builds: the same source, environment, and instructions give bit-for-bit identical artifacts | — | 2026-10-22 | <https://reproducible-builds.org/docs/definition/> |
| The Twelve-Factor App | — | 2026-10-16 (reviewed) | <https://12factor.net/> |
| CIS Benchmarks for images and clusters | — | 2026-10-16 (reviewed) | <https://www.cisecurity.org/cis-benchmarks> |
| DORA capabilities for deployment automation and the platform: continuous delivery, continuous integration, deployment automation, flexible infrastructure, and loosely coupled teams, plus the platform-engineering capability of the AI Capabilities Model | — | 2026-10-16 (reviewed) | <https://dora.dev/capabilities/platform-engineering/> |
| Platform as a product: an internal developer platform with golden paths, measured by developer adoption and time-to-first-deploy rather than by tickets | — | 2026-10-16 (reviewed) | <https://tag-app-delivery.cncf.io/whitepapers/platforms/> |
<!-- aidd:end -->

## Specify

- Say what runs where, with which permissions. A job running pull-request code never holds a secret. The plan or dry-run output is part of the Acceptance.
- Name the rollback: the previous workflow version, image digest, or state file.

## Implement

- On GitHub Actions, give each job the least `permissions:`, and pin each action and image by SHA or digest, the version in a comment. `pull_request_target` never checks out pull-request code. Untrusted input (titles, branch names) reaches `run:` only through an environment variable, never `${{ }}`.
- On GitLab, a fork's merge request pipeline gets no protected variable.
- A deploy job gets cloud access through OIDC (`id-token: write` on that job only), trusted only for its repository and protected environment.
- An update bot moves each pinned SHA and digest. The deploy checks the artifact's provenance first. Images follow their CIS Benchmark and run as non-root.
- Key caches by lockfile. Jobs have timeouts and concurrency groups, and artifacts have retention. Builds are hermetic, reproducible ([references/reproducible-builds.md](references/reproducible-builds.md)), and attested (SLSA provenance, an SBOM).
- aidd's default target: the pull-request pipeline takes under 10 minutes at the 90th percentile; change it to fit. A slower one is a defect, so fix it like a failing test, never by skipping a check. CI cost: [references/ci-cost.md](references/ci-cost.md).
- Package publishing is `aidd-team:package-publishing`'s, and the `dev_basics` default is `aidd-team:product-defaults`'s.

### Twelve-Factor

The build and deploy factors; the runtime ones are `aidd-team:observability`'s.

- **One codebase, many deploys.** One repository per deployable, and no fork per environment.
- **Dependencies declared and locked** in the manifest and the lockfile, never a tool that happens to be on the runner.
- **Separate build, release, run.** Build once into an image by digest. A release is that artifact plus one environment's config, so promote the same digest and never rebuild. A rollback is the previous release.
- **Dev/prod parity.** The same backing service in development, CI, and production, never a lighter stand-in. Keep commit-to-deploy time short.

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
| Shell check | every script parses and has no ShellCheck error | `shellcheck` on each script |
| Pipeline time | the pull-request pipeline stays under 10 minutes at the 90th percentile | a scheduled report, never a `tests` entry: the 90th percentile of wall time over the last 30 days of pull-request runs, measured as [references/ci-cost.md](references/ci-cost.md#read-the-bill) says |
| Build-once digest check | every job and deploy uses the one built digest; the image holds no environment file | a CI step that compares digests and lists the image's files |
| Reproducible build | a second clean build gives the same bytes | a second CI job, as [references/reproducible-builds.md](references/reproducible-builds.md) says |

- From `aidd-team:cloud-and-infrastructure`: IaC scanning, Plan or dry-run check.
- From `aidd-team:enterprise-controls`: Container scan and SBOM.

## Stop if

- A job that runs pull-request code would hold a secret, or `pull_request_target` would check it out.
- An action or image is referenced by a tag, not a SHA or digest.
- The plan destroys or replaces something the Spec did not name.

## Hand off

- Done: the pipeline change, its checks green, the plan attached. Next: the reviewer from the security pool. Needs: a secret, an environment, or a runner the platform team must create. Stopped at: none, or the stop rule that fired.
