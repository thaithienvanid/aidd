---
id: iac/trivy
type: opinionated
fills: [enterprise-controls:image-scanner]
default: true
implements: "enterprise-controls:Container scan and SBOM"
roles: [sre, security-engineer, reviewer]
when_changed: ["**/Dockerfile", Dockerfile, "**/Containerfile", ".github/workflows/**"]
why: "Trivy scans a built image for known vulnerabilities and misconfigurations from one binary, so the same tool gates the image in CI and the IaC in the cloud pack. Aqua Security maintains it under Apache-2.0."
reviewed: "2026-10-22"
maturity: established
tool:
  name: trivy
  registry: github
  package: aquasecurity/trivy
version_policy: current_stable
checked_version: "0.76.1"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "0.76.1"
source: https://api.github.com/repos/aquasecurity/trivy/releases/tags/v0.76.1
evidence: "\"tag_name\": \"v0.76.1\""
alternatives: [Grype, Clair, Docker Scout]
status: active
enforced_by:
  - name: image-scan
    command: [trivy, image, --exit-code, "1", --severity, "HIGH,CRITICAL"]
---

# Trivy scans the shipped image

It answers the image-scanner choice of `aidd-team:enterprise-controls`, and the cloud pack runs the same binary over IaC in its config scan. Trivy is under Apache-2.0 from Aqua Security. Grype, Clair, and Docker Scout are the alternatives where a team already runs one.

## What the team does

- Pin `trivy` at `pin`, and pin its vulnerability database too, so a scan is the same on every run and in CI.
- Fail the build on a HIGH or CRITICAL finding in a shipped image, and triage each one before it ships.
- Scan the image the pipeline publishes, by digest, not a tag that can move.
- Keep an ignore file in the repository, each entry with a reason and an expiry. A waiver is then a decision a person made, not a silent pass.
- Pair the scan with an SBOM for the same image, so a later advisory maps to what shipped.

## What the gate runs

One `image-scan` test runs `trivy image` at the pinned version over the published image, failing on exit code 1 for a HIGH or CRITICAL vulnerability.
