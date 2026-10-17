---
id: rust/cargo-lockfile
type: opinionated
fills: [ci-pipeline:package-manager]
default: true
implements: ci-pipeline:Dependencies declared and locked
roles: [developer, platform-engineer, reviewer]
when_changed: [Cargo.toml, "**/Cargo.toml", Cargo.lock]
why: "Cargo resolves and locks the Rust dependencies, and a committed Cargo.lock with --locked on every CI command makes each build use the graph that was reviewed."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://doc.rust-lang.org/cargo/commands/cargo-fetch.html
evidence: Asserts that the exact same dependencies and versions are used as when the existing Cargo.lock file was originally generated.
alternatives: [Cargo with a vendored dependency directory]
status: active
enforced_by:
  - name: lock
    command: [cargo, fetch, --locked]
---

# Cargo locks the Rust dependencies, and Cargo.lock is committed

It answers the package-manager choice of `aidd-team:ci-pipeline`. Its version is the toolchain's, which `rust/msrv` pins in `rust-toolchain.toml`.

## What the team does

- Commit `Cargo.lock`, for a library as well as a binary.
- Pass `--locked` to every cargo command in CI.
- Declare shared versions once in `[workspace.dependencies]`, and inherit them with `workspace = true`.
- Run `cargo update` in a change of its own, never as a side effect of another change.

## What the gate runs

One `tests` entry runs `cargo fetch --locked`. It fails when `Cargo.lock` is missing or no longer matches the manifests.
