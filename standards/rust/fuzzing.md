---
id: rust/fuzzing
type: opinionated
fills: [test-design:fuzzer]
default: true
implements: secure-coding:Parser fuzzing
roles: [developer, security-engineer, verifier, reviewer]
when_changed: ["**/*.rs", Cargo.toml, "**/Cargo.toml", Cargo.lock, "fuzz/**"]
why: "cargo-fuzz, from the rust-fuzz project, drives libFuzzer over a Rust function with coverage feedback, and the crash inputs it finds replay as plain files, so each one becomes a regression test."
reviewed: "2026-10-22"
maturity: established
tool:
  name: cargo-fuzz
  registry: crates
  package: cargo-fuzz
version_policy: current_stable
checked_version: "0.13.2"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "0.13.2"
source: https://github.com/rust-fuzz/cargo-fuzz
evidence: "This also needs a nightly compiler since it uses some unstable command-line flags."
alternatives: [cargo-afl, bolero]
status: active
enforced_by:
  - name: replay
    command: [sh, -c, "set -eu; for t in $(cargo +nightly-2026-10-15 fuzz list); do d=fuzz/regressions/$t; if [ -d \"$d\" ]; then cargo +nightly-2026-10-15 fuzz run \"$t\" \"$d\" -- -runs=0; fi; done"]
---

# cargo-fuzz runs libFuzzer over the Rust parsers

It answers the fuzzer choice of `aidd-team:test-design` for Rust, and runs the Parser fuzzing of `aidd-team:secure-coding`. cargo-fuzz is MIT or Apache-2.0, at the user's choice. It runs on Linux and macOS, on x86-64 and AArch64, and not on Windows.

## What the team does

- Run `cargo fuzz init`, then `cargo fuzz add <target>` for each parser, decoder, or other function that reads untrusted bytes. Take structured input through the `arbitrary` crate.
- Install cargo-fuzz at `pin` with `cargo install --locked`, and the dated nightly the gate's command names with rustup. Move that date in a change of its own, to a nightly at least a week old.
- Fuzz on a schedule, not on each change: a CI job runs each target for a set time, such as `cargo fuzz run <target> -- -max_total_time=600`, and keeps the corpus as a cache.
- When it finds a crash, shrink the input with `cargo fuzz tmin`, fix the code, and commit the input under `fuzz/regressions/<target>/` in the same change.
- Never delete an input from `fuzz/regressions/`.

## What the gate runs

One `tests` entry replays every input under `fuzz/regressions/` through its target once (`-runs=0`), with no new fuzzing, so the result is the same on every run. An input that still crashes fails the change.
