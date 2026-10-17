---
id: rust/cargo-workspace-boundaries
type: opinionated
fills: [modular-monolith:module-boundaries]
default: true
implements: modular-monolith:Boundary check
roles: [architect, developer, reviewer]
when_changed: [Cargo.toml, "**/Cargo.toml", Cargo.lock, boundaries-baseline.deny.toml]
why: "With one crate for each module, the compiler hides each crate's private items and Cargo refuses a cycle between crates; cargo-deny's wrappers then name the only crates that may depend on a module."
reviewed: "2026-10-16"
maturity: emerging
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://embarkstudios.github.io/cargo-deny/checks/bans/cfg.html
evidence: This field allows specific crates to have a direct dependency on the banned crate but denies all transitive dependencies on it.
alternatives: ["cargo-modules, for a monolith in one crate"]
status: active
enforced_by:
  - name: boundaries
    command: [cargo, deny, --config, boundaries-baseline.deny.toml, check, bans]
---

# One crate for each module, and cargo-deny, check the Rust module boundaries

It answers the module-boundaries choice of `aidd-team:modular-monolith` for Rust. Its tool is cargo-deny, which `rust/cargo-deny` pins and installs. cargo-deny is MIT or Apache-2.0, at the user's choice.

## What the team does

- Make each module a crate under `modules/`, a member of the Cargo workspace. Its `lib.rs` exports the API. Every other item is `pub(crate)` or private, so the compiler refuses its use from another crate.
- Declare a dependency on another module only in the crate's own `Cargo.toml`. Cargo's resolver refuses a cycle between normal dependencies. It allows one through dev-dependencies, so a reviewer checks those.
- Write the boundary rules in their own file, `boundaries-baseline.deny.toml`, not in `deny.toml`. Give each module crate one `[bans] deny` entry with `wrappers`: the crates that may depend on it directly.
- `baseline:module-boundaries` makes each change to that file major: it is the violations baseline. A change that adds a crate to a `wrappers` list needs an ADR.

## What the docs do not say

The cargo-deny docs do not say whether `wrappers` applies to path crates inside the workspace. A test on 2026-10-09 with cargo-deny 0.20.2 showed that it does: a module crate outside the `wrappers` list that depended on `orders` made the gate's command exit 2. Repeat that test after each upgrade of cargo-deny.

## What the gate runs

One `tests` entry runs the bans check of cargo-deny with that file. `--config` comes before `check`. A dependency on a module crate from a crate outside its `wrappers` fails the change.
