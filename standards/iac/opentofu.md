---
id: iac/opentofu
type: opinionated
fills: [cloud-and-infrastructure:iac-tool]
default: true
implements: cloud-and-infrastructure:Plan or dry-run check
roles: [platform-engineer, architect, security-engineer, reviewer]
when_changed: ["**/*.tf", "**/*.tofu", "**/*.tfvars", ".terraform.lock.hcl", ".tflint.hcl"]
why: "OpenTofu is an open-source infrastructure-as-code tool under MPL-2.0 that reads the Terraform language and providers, and TFLint catches provider errors and unused code that tofu validate misses."
reviewed: "2026-10-16"
maturity: established
tool:
  name: opentofu
  registry: github
  package: opentofu/opentofu
version_policy: current_stable
checked_version: "1.13.1"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [Terraform, Pulumi, AWS CDK, "Wrangler, for a project only on Cloudflare"]
status: active
source: https://opentofu.org/docs/cli/commands/fmt/
evidence: The tofu fmt command is used to rewrite OpenTofu configuration files to a canonical format and style.
enforced_by:
  - name: fmt
    command: [tofu, fmt, -check, -recursive]
  - name: lint-init
    command: [tflint, --recursive, --init]
  - name: lint
    command: [tflint, --recursive]
---

# OpenTofu defines the infrastructure, and TFLint checks it

It answers the iac-tool choice of `aidd-team:cloud-and-infrastructure` for a project on AWS, Google Cloud, or more than one provider.

## What the team does

- Pin OpenTofu with `required_version`, and every provider in `required_providers`. Commit `.terraform.lock.hcl`. CI installs the OpenTofu release that `required_version` allows.
- Keep the state in a remote backend with locking. Turn on OpenTofu's state encryption.
- Install TFLint at one stated release in CI. Commit `.tflint.hcl` with the ruleset plugin of each provider in use, each at a pinned version, and run `tflint --recursive --init` before the check.
- Write one plan for each environment in CI as JSON (`tofu show -json`), so `cost/pr-cost-delta-threshold` and `cost/policy-caps` read the same plan the reviewer sees.
- Apply only from CI, after the plan is approved with the change.
- Keep modules small and versioned. A module from a registry is pinned to an exact version.

## What the gate runs

Three `tests` entries: `tofu fmt -check -recursive`, then `tflint --recursive --init`, which installs the plugins `.tflint.hcl` pins, then `tflint --recursive`. A file out of format or a lint finding fails the change.
