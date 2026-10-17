---
id: iac/terraform
type: opinionated
fills: [cloud-and-infrastructure:iac-tool]
default: false
implements: cloud-and-infrastructure:Plan or dry-run check
roles: [platform-engineer, architect, security-engineer, reviewer]
when_changed: ["**/*.tf", "**/*.tfvars", ".terraform.lock.hcl", ".tflint.hcl"]
why: "Terraform is the tool that defined the Terraform language and providers, so a team that already runs it, or HCP Terraform, keeps its code and state. TFLint catches provider errors that terraform validate misses."
reviewed: "2026-10-16"
maturity: established
tool:
  name: terraform
  registry: github
  package: hashicorp/terraform
version_policy: current_stable
checked_version: "1.16.5"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://raw.githubusercontent.com/hashicorp/terraform/main/LICENSE
evidence: "Licensed Work:        Terraform Version 1.6.0 or later."
alternatives: [OpenTofu, Pulumi, AWS CDK, "Wrangler, for a project only on Cloudflare"]
status: active
enforced_by:
  - name: fmt
    command: [terraform, fmt, -check, -recursive]
  - name: lint-init
    command: [tflint, --recursive, --init]
  - name: lint
    command: [tflint, --recursive]
---

# Terraform defines the infrastructure, and TFLint checks it

It answers the iac-tool choice of `aidd-team:cloud-and-infrastructure`. aidd's default is `iac/opentofu`. This option is for a team that keeps Terraform.

## License

Terraform 1.6.0 and later is under the Business Source License 1.1 (BSL 1.1), and IBM is the licensor. BSL 1.1 is not an open-source license. It allows production use, but not in a product that you offer to third parties, hosted or embedded, and that competes with IBM's paid versions. Each version changes to MPL 2.0 four years after it is published.

## What the team does

- Set `required_version` to the Terraform release that CI installs, and pin each provider in `required_providers`. Commit `.terraform.lock.hcl`, which `terraform init` writes.
- Store the state in a remote backend that locks it for each run.
- Run TFLint at a stated release. Commit `.tflint.hcl`, which pins the ruleset plugin of each provider in use, and let CI run `tflint --recursive --init` first.
- In CI, save one plan for each environment and its JSON from `terraform show -json`. `cost/pr-cost-delta-threshold` and `cost/policy-caps` read that JSON.
- Apply only from CI, once the change and its plan are approved.
- Pin each module from a registry to an exact version.

## What the gate runs

Three `tests` entries: `terraform fmt -check -recursive`, then `tflint --recursive --init`, which installs the plugins `.tflint.hcl` pins, then `tflint --recursive`. A file that is not in the canonical format, or a TFLint finding, fails the change.
