---
id: rust/cargo-modules
type: opinionated
fills: [modular-monolith:module-boundaries]
default: false
implements: modular-monolith:Boundary check
roles: [architect, developer, reviewer]
when_changed: ["**/*.rs", Cargo.toml, Cargo.lock]
why: "For a monolith in one crate, Rust's privacy hides each module's private items, and cargo-modules fails on a cycle in the crate's module graph."
reviewed: "2026-10-16"
maturity: emerging
tool:
  name: cargo-modules
  registry: crates
  package: cargo-modules
version_policy: current_stable
checked_version: "0.27.0"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://github.com/regexident/cargo-modules
evidence: If found it will search for cycles in the directed graph and return an error for any cycles it found.
pin: "0.27.0"
alternatives: ["one crate for each module, with cargo-deny"]
status: active
enforced_by:
  - name: acyclic
    command: [cargo, modules, dependencies, --lib, --acyclic]
---

# cargo-modules checks a Rust monolith in one crate

It answers the module-boundaries choice of `aidd-team:modular-monolith` for a Rust service that keeps its modules in one crate. cargo-modules is under the Mozilla Public License 2.0, which covers the tool, not the code it checks. `rust/cargo-workspace-boundaries` stays the default.

## What the team does

- Install cargo-modules at `pin` with `cargo install --locked`.
- Make each module a top-level `mod` of the library crate. Make its `api` module `pub`, and keep its `internal` module private, so the compiler refuses a path into it from a sibling module.
- Keep one library target, so the check reads the whole module graph.
- Break a cycle that the check reports with an event or a merge of the two modules. Never hide one: the check has no ignore list.
- `--acyclic` sees a cycle only where modules import each other whole, such as `use crate::billing;`. Imports of items, such as `use crate::billing::charge;` and `use crate::orders::place;`, pass. So a reviewer keeps the module graph acyclic: draw it from the `use` lines between modules, and refuse an import that closes a loop.
- Move to one crate for each module when the crate grows. Then Cargo itself refuses a cycle between modules.

## What the gate runs

One `tests` entry builds the module graph of the library target in acyclic mode. A cycle of whole-module imports is an error, and it fails the change.
