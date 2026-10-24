---
id: rust/rustfmt
type: opinionated
fills: [ci-pipeline:formatter]
default: true
implements: product-defaults:dev_basics
roles: [developer, reviewer]
when_changed: ["**/*.rs", rustfmt.toml, ".rustfmt.toml"]
why: "rustfmt is the Rust project's own formatter and ships as a component of every toolchain, so the pinned toolchain fixes the layout on every machine."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://github.com/rust-lang/rustfmt
evidence: "When running with --check, Rustfmt will exit with 0 if Rustfmt would not make any formatting changes to the input, and 1 if Rustfmt would make changes."
status: active
enforced_by:
  - name: format
    command: [cargo, fmt, --all, --check]
---

# rustfmt formats the Rust code

It answers the formatter choice of `aidd-team:ci-pipeline`. Its version is the toolchain's, which `rust/msrv` pins in `rust-toolchain.toml`.

## What the team does

- List `rustfmt` under `components` in `rust-toolchain.toml`, so each machine installs the same one.
- Keep `rustfmt.toml` to stable options, such as `edition` and `max_width`. Nightly-only options do nothing on a stable toolchain.
- Run `cargo fmt --all` in the pre-commit hook.
- A `#[rustfmt::skip]` carries a comment with its reason.

## What the gate runs

One `tests` entry runs `cargo fmt --all --check` on every workspace member. It exits with 1 when any file would change.
