# Security policy

## Report a vulnerability

Use GitHub's private vulnerability reporting on this repository ("Security" → "Report a vulnerability", or <https://github.com/thaithienvanid/aidd/security/advisories/new>). Do not open a public issue. Expect an acknowledgement within 3 business days, and a fix or mitigation plan within 30 days.

## In scope

- Any way for a change to reach a protected branch while `aidd/gate` should have failed or stayed pending. That includes forged evidence, approval replay, separation-of-duties bypass, protected-path evasion, config tampering, and trusting PR-controlled code in the gate job.
- Glob, schema, or TOML parsing bugs that change a decision.
- Leaks of tokens or secrets through gate output, events, or artifacts.
- Template workflows that grant more permissions than their job needs.

## Trust model

[METHOD.md §14](docs/METHOD.md#14-platform-bindings-and-trust) owns the full model; this is a summary. Known limits are in [RATIONALE.md](docs/RATIONALE.md#known-limits-in-100).

- **The gate job is trusted.** It runs from the default branch, reads the PR/MR head as git objects only, runs Policy from the base branch without tokens, and never executes the change's code.
- **The status source must be pinned** to a dedicated GitHub App. Without it, anyone with write access can post `aidd/gate`, and the gate is advisory.
- **The gate runs aidd from the reusable workflow's own commit**, with no package build, and keeps the App key only in the `aidd-gate` environment.
- **The test job is untrusted.** The platform token is present in the job and stripped from every test command. aidd rejects stale, missing, substituted, self-reported, and cross-PR evidence, but it cannot make hostile test code honest: a malicious change to tests, build scripts, or dependencies can make its own tests lie. The Spec approval and Merge approval human reviews are the control for that.
- **The config is read from the base branch**, and changing it is a protected, major change.
- **GitLab** is only as trustworthy as the pipeline execution policy that injects the gate. Fork MR pipelines fail closed.

## Data handling

The verifier reads the change through the platform's API and writes a status, a record, and an event, and it carries no telemetry. At run time it reaches the platform's API and the artifact storage that API redirects evidence downloads to, and beyond those only what you configure: an `extends` parent or org preset fetched by URL, and the attestation endpoints when `evidence.signer_workflow` is set ([the full egress list](docs/PLATFORMS.md#github-enterprise-server-and-restricted-actions)). What it reads, writes, and keeps, and for how long, is listed in [docs/ENTERPRISE.md](docs/ENTERPRISE.md#7-data-handling-and-privacy).

## Supported versions

| Version | Supported | Security fixes |
| --- | --- | --- |
| 1.x, latest minor | yes | yes |
| 1.x, older minors | no | no; upgrade to the latest minor |

Nothing is released yet: 1.0.0 will be the first version. There is no fixed release cadence, so "supported" means the latest minor of the latest major. An older minor keeps working — the gate is versioned through `aidd_version` — but it receives no fixes. Supported Pythons are 3.11 through 3.14, the versions in the classifiers of `pyproject.toml`, each tested on Linux, macOS, and Windows. CI also tests 3.15 as a prerelease; it is not supported until it is released and listed. A Python that leaves the CI matrix leaves support here too.
