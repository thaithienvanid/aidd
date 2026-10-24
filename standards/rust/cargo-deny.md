---
id: rust/cargo-deny
type: opinionated
fills: [ci-pipeline:dependency-audit]
default: true
implements: enterprise-controls:Dependency scan
roles: [developer, security-engineer, compliance-analyst, reviewer]
when_changed: [Cargo.toml, "**/Cargo.toml", Cargo.lock, deny.toml]
why: "cargo-deny reads the RustSec database for Cargo.lock and also checks licenses, banned or duplicate crates, and crate sources, which a vulnerability scan alone does not cover."
reviewed: "2026-10-16"
maturity: established
tool:
  name: cargo-deny
  registry: crates
  package: cargo-deny
version_policy: current_stable
checked_version: "0.20.2"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
pin: "0.20.2"
source: https://embarkstudios.github.io/cargo-deny/
evidence: cargo-deny is a cargo plugin that lets you lint your project's dependency graph to ensure all your dependencies conform to your expectations and requirements.
alternatives: [cargo-audit, OSV-Scanner alone]
status: active
enforced_by:
  - name: deny
    command: [cargo, deny, check]
---

# cargo-deny adds Rust's own audit to the dependency scan

It answers the dependency-audit choice of `aidd-team:ci-pipeline` for Rust.

## What the team does

- Keep the Dependency scan of `aidd-team:enterprise-controls`: OSV-Scanner still reads `Cargo.lock`. cargo-deny is the Rust addition, never its replacement.
- Commit `deny.toml` (`cargo deny init` writes one) with all four checks on: advisories, bans, licenses, and sources.
- The advisories check also reports crates marked unmaintained or yanked.
- List the allowed SPDX license ids. Allow crates only from crates.io and named git hosts.
- Each `ignore` entry names the advisory id and the reason.
- Install the binary at `pin`, with `cargo install --locked` or the project's GitHub Action.

## What the gate runs

One `tests` entry runs `cargo deny check` against `Cargo.lock`. Any error from the four checks fails the change.
