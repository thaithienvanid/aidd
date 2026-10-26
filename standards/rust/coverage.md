---
id: rust/coverage
type: opinionated
fills: [test-design:coverage-tool]
default: true
implements: test-design:Review
roles: [developer, verifier, reviewer]
when_changed: ["**/*.rs", Cargo.toml, "**/Cargo.toml", Cargo.lock, ".config/nextest.toml"]
why: "cargo-llvm-cov measures coverage with rustc's own LLVM instrumentation and runs the tests through cargo-nextest, so the coverage run is the test run the team already trusts."
reviewed: "2026-10-22"
maturity: established
tool:
  name: cargo-llvm-cov
  registry: crates
  package: cargo-llvm-cov
version_policy: current_stable
checked_version: "0.9.1"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "0.9.1"
source: https://github.com/taiki-e/cargo-llvm-cov
evidence: "Support for doc tests is unstable and has known issues."
alternatives: [cargo-tarpaulin, grcov]
status: active
enforced_by:
  - name: coverage
    command: [sh, -c, "cargo llvm-cov nextest --workspace --locked --fail-under-lines \"${COVERAGE_MIN_LINES:?set COVERAGE_MIN_LINES to the team floor, a percent of lines}\""]
---

# cargo-llvm-cov measures the coverage of the Rust tests

It answers the coverage-tool choice of `aidd-team:test-design` for Rust. Its runner is cargo-nextest, which `rust/cargo-nextest` pins. cargo-llvm-cov is MIT or Apache-2.0, at the user's choice.

## What the team does

- Install it at `pin` in CI, from the pre-built binary or with `cargo install --locked`, and add the `llvm-tools-preview` component to `rust-toolchain.toml`.
- Set `COVERAGE_MIN_LINES` in the CI environment: the team's floor, a percent of lines. aidd sets no value, and the check fails until the team sets one.
- Raise the floor in a change of its own when coverage rises. Never lower it to let a change pass.
- Count line coverage on stable Rust. Branch coverage and doctest coverage need nightly, so leave them out of the floor.
- Keep the code no test reaches small, such as a thin `main` that wires the app. The `coverage(off)` attribute works on nightly only, so it hides nothing from this floor.
- Upload the lcov report (`cargo llvm-cov report --lcov`) as a CI artifact, so the reviewer sees the lines a change left untested.

## What the gate runs

One `tests` entry runs the workspace tests through cargo-nextest under coverage. It exits with 1 when line coverage falls below `COVERAGE_MIN_LINES`, and it fails while that variable is unset.
