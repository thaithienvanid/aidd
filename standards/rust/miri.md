---
id: rust/miri
type: opinionated
fills: [test-design:undefined-behavior-check]
implements: secure-coding:Implement
default: true
roles: [developer, security-engineer, reviewer]
when_changed: ["**/*.rs", Cargo.toml, "**/Cargo.toml", Cargo.lock]
why: "Miri, from the Rust project, runs the tests of a crate in an interpreter that checks each unsafe operation, so undefined behaviour that a normal test run hides fails the run."
reviewed: "2026-10-22"
maturity: emerging
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "nightly-2026-10-15"
source: https://github.com/rust-lang/miri
evidence: "It can run binaries and test suites of cargo projects and detect unsafe code that fails to uphold its safety requirements."
alternatives: [AddressSanitizer on nightly, Valgrind]
status: active
enforced_by:
  - name: miri
    command: [sh, -c, "set -eu; : \"${MIRI_CRATES:?set MIRI_CRATES to the -p flags of each crate with unsafe code}\"; cargo +nightly-2026-10-15 miri test --locked $MIRI_CRATES"]
---

# Miri runs the tests of every Rust crate that holds unsafe code

It answers the undefined-behavior-check choice of `aidd-team:test-design` for Rust. Miri is MIT or Apache-2.0, at the user's choice. It ships only as a nightly component, so this standard is emerging.

## What the team does

- Put `#![forbid(unsafe_code)]` at the root of each crate with no unsafe code. A crate that needs `unsafe` drops that line and joins `MIRI_CRATES`.
- Set `MIRI_CRATES` in the CI environment to a `-p <crate>` flag for each such crate. The check fails while it is unset.
- Keep the unsafe code in small crates with fast unit tests, because Miri runs far slower than native code.
- Install the toolchain `pin` names: `rustup toolchain install <pin> --component miri`. It is a dated nightly at least a week old, never a floating `nightly`. Move it in a change of its own.
- Mark a test Miri cannot run, such as one that calls a foreign function, with `#[cfg_attr(miri, ignore)]` and a comment that says why.
- A passing run is not a proof of soundness. Miri checks only the paths the tests take.

## What the gate runs

One `tests` entry runs `cargo miri test` on the crates `MIRI_CRATES` names. Undefined behaviour, a memory leak, or a failing test fails the change.
