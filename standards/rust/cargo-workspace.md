---
id: rust/cargo-workspace
type: opinionated
fills: [ci-pipeline:workspace]
default: true
implements: ci-pipeline:Dependencies declared and locked
roles: [developer, sre, reviewer]
when_changed: [Cargo.toml, "**/Cargo.toml", Cargo.lock]
why: "A Cargo workspace builds every app, module, and package crate together with one Cargo.lock and one output directory, so they all use one resolved set of dependencies."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://doc.rust-lang.org/cargo/reference/workspaces.html
evidence: All packages share a common Cargo.lock file which resides in the workspace root.
alternatives: [one crate with a module for each business module]
status: active
enforced_by:
  - name: build
    command: [cargo, build, --workspace, --locked]
---

# A Cargo workspace holds the Rust apps, modules, and packages

It answers the workspace choice of `aidd-team:ci-pipeline` for Rust. Its tool is Cargo, which `rust/msrv` pins with the toolchain. Cargo is MIT or Apache-2.0, at the user's choice.

## What the team does

- Write a virtual manifest at the root: `[workspace]` with `members = ["apps/*", "modules/*", "packages/*"]` and `resolver = "3"`.
- Set the shared package fields once in `[workspace.package]`, and inherit them in each crate.
- Refer to a sibling with a `path` dependency, declared in the crate that uses it.
- Set `publish = false` on each crate that is not a library for other repositories.

## What the gate runs

One `tests` entry builds every member with `--locked`. A member that does not compile fails the change, and so does a `Cargo.lock` that the build would change.
