---
name: ci-pipeline
description: "Practice skill: change CI, CD, or build pipelines safely. Use when a Task touches a CI or CD workflow, a GitHub Actions or GitLab CI file, a build script, a Dockerfile or container image, a release job, or infrastructure as code, or when someone says the pipeline is red, the build is slow, pin the actions, secrets in CI, OIDC, supply chain, SBOM, or provenance: least privilege, pinned actions, OIDC over secrets, provenance, reproducible builds, and the test commands that prove them."
metadata:
  checked: "2026-09-25"
---

# CI pipeline

**Use it when** a Task touches a workflow, a build script, a container image, or infrastructure as code. These are protected or baseline paths, so expect major and the security pool. The `aidd-team:cloud-and-infrastructure` pack says what applies; this skill is how to do the work.

**Do not use when** the change touches no pipeline, build, or artifact; a test command inside a Spec is the tester's, not a pipeline change.

## Standards

- SLSA v1.2 build provenance.
- OpenSSF Scorecard.
- Reproducible builds.
- SBOM (CycloneDX or SPDX).
- Least-privilege CI with OIDC federation and actions pinned by commit SHA.
- CIS Benchmarks for images and clusters.

## Specify, before Spec approval

- Say what runs where and with which permissions; a job that runs pull-request code never holds a secret; the plan or dry-run output is part of the Acceptance.
- Name the rollback: the previous workflow version, image digest, or state file.

## Implement

- `permissions:` is set per job to the minimum; every action and image is pinned by SHA or digest with the version in a comment; `pull_request_target` never checks out pull-request code.
- Untrusted input (titles, bodies, branch names) reaches a `run:` step only through an environment variable, never through `${{ }}` inside the script.
- Caches are keyed by lockfile; jobs have timeouts and concurrency groups; artifacts have retention; builds are hermetic and attested.

## Test commands

- `actionlint`; a workflow security scanner such as zizmor (emerging); `sh -n` on every shell script; IaC scanning (Checkov, Trivy config, KICS); image scanning (Trivy, Grype) with an SBOM (Syft); a plan or dry-run diff checked by a script for unnamed destroys or replaces.

## Review

- Any elevated permission, any unpinned reference, any secret reachable from pull-request code, any drift between the plan and the Spec.

## Hand off

- Done: the pipeline change with its checks green and the plan attached. Next: the reviewer from the security pool. Needs: a secret, an environment, or a runner the platform team must create. Stopped at: none, or the stop rule that fired.
