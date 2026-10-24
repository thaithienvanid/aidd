---
id: rust/msrv
type: opinionated
fills: [ci-pipeline:language-version]
default: true
implements: ci-pipeline:Dependencies declared and locked
roles: [developer, sre, reviewer]
when_changed: [rust-toolchain.toml, rust-toolchain, Cargo.toml, "**/Cargo.toml", Cargo.lock, "**/*.rs"]
why: "rust-toolchain.toml pins the exact compiler every machine builds with, and rust-version states the oldest one the code supports, so both the build and the promise are files that CI reads."
reviewed: "2026-10-16"
maturity: established
tool:
  name: rust
  registry: github
  package: rust-lang/rust
version_policy: current_stable
checked_version: "1.99.1"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "1.99.1"
source: https://doc.rust-lang.org/cargo/reference/rust-version.html
evidence: The rust-version field is an optional key that tells cargo what version of the Rust toolchain you support for your package.
alternatives: [the latest stable toolchain with no declared MSRV, a pinned nightly toolchain]
status: active
enforced_by:
  - name: msrv
    command: [cargo, hack, check, --rust-version, --workspace, --all-targets, --locked]
---

# rust-toolchain.toml pins Rust, and rust-version declares the MSRV

It answers the language-version choice of `aidd-team:ci-pipeline`.

## What the team does

- In `rust-toolchain.toml`, set `channel` to an exact stable release, with the `rustfmt` and `clippy` components. Move it forward after each stable release through `aidd-team:dependency-upgrade`.
- Set `rust-version` once under `[workspace.package]` and inherit it with `rust-version.workspace = true`. That is the MSRV: the oldest compiler the code promises to build on.
- Raise the MSRV on purpose, in a change of its own. With resolver 3, the 2024 edition's default, Cargo prefers dependency versions that support it.
- CI installs cargo-hack at an exact version (`cargo install --locked cargo-hack@0.6.45`, the newest on the `checked` day) and the MSRV toolchain with rustup, never whatever cargo-hack the runner has. `pin` is the toolchain, not cargo-hack.

## What the gate runs

One `tests` entry runs `cargo hack check --rust-version`. It builds each workspace member with the compiler its `rust-version` names, so the declared minimum is tested.
