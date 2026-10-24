---
id: rust/criterion
type: opinionated
fills: [performance:benchmark-tool]
default: true
implements: performance:Regression guard
roles: [developer, verifier, reviewer]
when_changed: ["benches/**", "**/benches/**", Cargo.toml, "**/Cargo.toml"]
why: "Criterion.rs runs Rust benchmarks on stable Rust, and compares each run with a saved baseline. It reports a regression only with strong statistical evidence beyond the noise threshold."
reviewed: "2026-10-22"
maturity: established
tool:
  name: criterion
  registry: crates
  package: criterion
version_policy: current_stable
checked_version: "0.8.2"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "0.8.2"
source: https://crates.io/api/v1/crates/criterion
evidence: "\"max_stable_version\":\"0.8.2\""
alternatives: [divan, hyperfine for a whole program]
status: active
enforced_by:
  - name: bench
    command: [cargo, test, --benches, --locked]
---

# Criterion benchmarks the Rust code

It answers the benchmark-tool choice of `aidd-team:performance` for Rust. Criterion.rs is dual-licensed under Apache-2.0 and MIT.

## What the team does

- Add `criterion` at `pin` under `[dev-dependencies]`, and give each file in `benches/` a `[[bench]]` entry with `harness = false`.
- Wrap each input and result in `std::hint::black_box`, so the compiler cannot remove the work.
- In the Regression guard, run `cargo bench -- --save-baseline base` on the base. Then run `cargo bench -- --baseline base` on the head, in the same job on the same runner.
- Read Criterion's verdict for each benchmark. Fail the guard on "Performance has regressed" when the change is past the Spec's bound. "No change in performance detected" passes.
- Keep `target/criterion` out of the repository, so a baseline from another machine is never read.

## What the gate runs

One `bench` test runs `cargo test --benches`, which runs each benchmark once without measuring it. A benchmark that no longer builds or panics fails the change.
