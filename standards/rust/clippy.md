+++
id = "rust/clippy"
type = "opinionated"
fills = ["ci-pipeline:linter"]
default = true
implements = "product-defaults:dev_basics"
roles = ["developer", "reviewer"]
when_changed = ["**/*.rs", "Cargo.toml", "**/Cargo.toml", "Cargo.lock", "clippy.toml", ".clippy.toml"]
why = "Clippy is the Rust project's own linter, shipped with each toolchain, and denying every warning in CI keeps the code free of both its lints and the compiler's."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
source = "https://doc.rust-lang.org/clippy/usage.html"
evidence = "Since Cargo 1.97, the recommended way to do this is by using the build.warnings config option."
status = "active"
enforced_by = [
  { name = "lint", command = ["cargo", "clippy", "--workspace", "--all-targets", "--locked", "--config", "build.warnings=\"deny\""] },
]
+++

# Clippy checks the Rust code, and any warning fails

It answers the linter choice of `aidd-team:ci-pipeline`. Its version is the toolchain's, which `rust/msrv` pins in `rust-toolchain.toml`.

## What the team does

- List `clippy` under `components` in `rust-toolchain.toml`.
- Set lint levels once, in `[workspace.lints.clippy]` of the root `Cargo.toml`, and inherit them with `lints.workspace = true` in each member.
- Deny warnings through Cargo's `build.warnings` setting rather than `-D warnings`, which throws away the build cache.
- Add `--all-features` to a copy only when every feature is additive; crates with mutually exclusive features fail to build with it.
- Write `#[expect(clippy::lint_name, reason = "...")]` instead of `#[allow]`, so a lint that stops firing is reported.

## What the gate runs

One `[[tests]]` entry runs Clippy over every target, with the default features and `build.warnings` set to `deny`. Any warning, from Clippy or from rustc, fails the change.
