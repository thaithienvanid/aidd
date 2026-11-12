---
name: ci-pipeline
description: "Practice skill: change CI, CD, or build pipelines safely. Use in an aidd repository when a Task touches a workflow, build script, Dockerfile, release job, or IaC, or CI is red."
metadata:
  checked: "2026-10-22"
---

# CI pipeline

**Use it when** a Task touches a workflow, a build script, a container image, or infrastructure as code. `aidd risk --paths` gives the route: these files are in the `ci` and `infra` areas. The `aidd-packs:cloud-and-infrastructure` pack says what applies, and this skill is how to do the work.

**Do not use when** the change touches no pipeline, build, or artifact. A test command in a Spec is the verifier's, not a pipeline change.

## Standards

<!-- aidd:gen practice:ci-pipeline -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| SLSA | v1.2, 2025 | 2026-11-10 | <https://slsa.dev/> |
| SBOM in CycloneDX (with ML-BOM) or SPDX, and VEX | 1.7.2 | 2026-10-16 | <https://github.com/CycloneDX/specification/releases/tag/1.7.2> |
| Least-privilege CI: OIDC federation over long-lived secrets, actions pinned by commit SHA | — | 2026-10-16 | <https://docs.github.com/en/actions/concepts/security/openid-connect> |
| Reproducible builds: the same source, environment, and instructions give bit-for-bit identical artifacts | — | 2026-10-22 | <https://reproducible-builds.org/docs/definition/> |
| The Twelve-Factor App | — | 2026-10-16 | <https://12factor.net/> |
| CIS Benchmarks for images and clusters | — | 2026-10-16 | <https://www.cisecurity.org/cis-benchmarks> |
| DORA capabilities for deployment automation and the platform: continuous delivery, continuous integration, deployment automation, flexible infrastructure, and loosely coupled teams, plus the platform-engineering capability of the AI Capabilities Model | — | 2026-10-16 | <https://dora.dev/capabilities/platform-engineering/> |
| Platform as a product: an internal developer platform with golden paths, measured by developer adoption and time-to-first-deploy rather than by tickets | — | 2026-10-16 | <https://tag-app-delivery.cncf.io/whitepapers/platforms/> |
<!-- aidd:end -->

## Specify

- Say what runs where, with which permissions. A job running pull-request code never holds a secret. The plan or dry-run output is part of the Acceptance.
- Name the rollback: the previous workflow version, image digest, or state file.

## Implement

- On GitHub Actions, give each job the least `permissions:`, and pin each action and image by SHA or digest, the version in a comment. `pull_request_target` never checks out pull-request code. Untrusted input (titles, branch names) reaches `run:` only through an environment variable, never `${{ }}`.
- On GitLab, keep each secret a protected variable. A fork's merge request pipeline gets none of them, but one run in the parent project gets its other variables, so a person reads the diff first.
- A step never pipes a script into a shell (`curl … | sh`) or fetches one at a mutable ref, such as a branch. Codecov's bash uploader, altered in 2021, sent CI environment variables to an outside server.
- A job that holds a secret installs with `npm ci --ignore-scripts`, or the package manager's equivalent. The nx releases of 2025 read credentials in a `postinstall` script. Workflow lint misses both rules.
- A deploy job gets cloud access through OIDC (`id-token: write` on that job only), trusted only for its repository and protected environment.
- An update bot moves each pinned SHA and digest. The deploy checks the artifact's provenance first. Images follow their CIS Benchmark and run as non-root.
- Key caches by lockfile. Jobs have timeouts and concurrency groups, and artifacts have retention. Builds are hermetic, reproducible ([references/reproducible-builds.md](references/reproducible-builds.md)), and attested (SLSA provenance, an SBOM).
- Local checks and the pipeline run the same commands. Each job calls the one command a person runs. That command covers every check the pipeline runs on a change, the secret scan included, except one with a named reason to run only in the pipeline ([references/reproducible-builds.md](references/reproducible-builds.md#the-same-checks-on-every-machine)).
- Test the oldest and the newest runtime version the project supports. Run each platform the release builds on before the release job, in a container where you can, and name the gap where you cannot.
- A failing test with no defect behind it is a finding with an owner, never a re-run until green (hard rule 7 of the aidd skill). Its rerun count is data in the test command, and a late pass is reported as flaky.
- aidd's default target: the pull-request pipeline takes under 10 minutes at the 90th percentile; change it to fit. A slower one is a defect, so fix it like a failing test, never by skipping a check. CI cost: [references/ci-cost.md](references/ci-cost.md).
- Package publishing is `aidd-packs:package-publishing`'s, and the `dev_basics` default is `aidd-team:product-defaults`'s.

### Twelve-Factor

The build and deploy factors; the runtime ones are `aidd-team:observability`'s.

- **One codebase, many deploys.** One repository per deployable, and no fork per environment.
- **Dependencies declared and locked** in the manifest and the lockfile, never a tool that happens to be on the runner.
- **Separate build, release, run.** Build once into an image by digest. A release is that artifact plus one environment's config, so promote the same digest and never rebuild. A rollback is the previous release.
- **Dev/prod parity.** The same backing service in development, CI, and production, never a lighter stand-in. Keep commit-to-deploy time short.

Test: the Build-once digest check below, and an integration job that runs on the production backing service's type and major version.

## Review

- Flag any elevated permission, unpinned reference, secret reachable from pull-request code, or drift between the plan and the Spec. Flag a check that only the pipeline can run, a workflow step that holds its own copy of a check's lines, and a retry around a test.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Workflow lint | no workflow syntax error, over-broad permission, or injectable expression | `actionlint` (v1.7.12) and `uvx zizmor==1.32.0 .` (zizmor emerging) |
| Shell check | every script parses and has no ShellCheck error | `shellcheck` on each script |
| Pipeline time | the pull-request pipeline stays under 10 minutes at the 90th percentile | a scheduled report, never a `tests` entry: the 90th percentile of wall time over the last 30 days of pull-request runs, measured as [references/ci-cost.md](references/ci-cost.md#read-the-bill) says |
| Build-once digest check | every job and deploy uses the one built digest; the image holds no environment file | a CI step that compares digests and lists the image's files |
| Local run | every check the pipeline runs on a change, except one with a named reason, also runs on the working tree, secret scan included | one project command, which each pipeline job calls, so the two cannot drift |
| Reproducible build | a second clean build gives the same bytes | a second CI job, as [references/reproducible-builds.md](references/reproducible-builds.md) says |

- From `aidd-packs:cloud-and-infrastructure`: IaC scanning, Plan or dry-run check.
- From `aidd-packs:enterprise-controls`: Container scan and SBOM.

## Stop if

- A job that runs pull-request code would hold a secret, or `pull_request_target` would check it out.
- An action or image is referenced by a tag, not a SHA or digest.
- The plan destroys or replaces something the Spec did not name.
- A test would be re-run until it passes, or a check would run only in the pipeline with no named reason.

## Hand off

- Done: the pipeline change, its checks green, the plan attached. Next role: the reviewer, then a person who reviews security. Needs: a secret, an environment, or a runner the platform team must create. Stopped at: none, or the stop rule's code.
