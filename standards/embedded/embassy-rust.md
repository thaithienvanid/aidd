---
id: embedded/embassy-rust
type: opinionated
fills: [embedded-automotive-industrial:rtos]
implements: embedded-automotive-industrial:HIL or simulation run
roles: [architect, developer, verifier, reviewer]
when_changed: ["**/*.rs", Cargo.toml, "**/Cargo.toml", Cargo.lock, .cargo/config.toml, memory.x, rust-toolchain.toml]
why: "Embassy runs async Rust tasks on a microcontroller without an RTOS, and its HALs implement the embedded-hal 1.0 traits, so drivers are portable and memory safety comes from the compiler."
reviewed: "2026-10-22"
maturity: emerging
tool:
  name: embassy-executor
  registry: crates
  package: embassy-executor
version_policy: current_stable
checked_version: "0.10.0"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "0.10"
source: https://embassy.dev/book/
evidence: The Embassy project maintains HALs for select hardware, but you can still use HALs from other projects with Embassy.
alternatives: [RTIC, Zephyr with its Rust support, bare metal with a cortex-m-rt main loop]
status: active
enforced_by:
  - name: firmware
    command: [cargo, build, --release, --locked]
---

# Embassy runs firmware written in Rust

It answers the rtos choice of `aidd-team:embedded-automotive-industrial` for Rust. Embassy is under the MIT license or the Apache License 2.0, at your choice. It is emerging: its executor is not yet 1.0, so a minor release can break the API. Choose it only when the Spec says why Rust pays off.

## What the team does

- Set the chip's target in `.cargo/config.toml`, with `probe-rs run --chip <chip>` as the runner, and pin the toolchain in `rust-toolchain.toml`.
- Pin each Embassy crate to a crates.io release in `Cargo.toml` and commit `Cargo.lock`. A git dependency names a full commit, never a branch.
- Write drivers against the embedded-hal 1.0 and embedded-hal-async traits, not a HAL's own types, so a host test can pass a mock.
- Log with defmt and defmt-rtt, which send short indexes instead of strings, so logging stays cheap in time and flash.
- Keep the logic in crates that build for the host, and test them there with the project's Rust test runner from the `rust/` standards.
- Run the built firmware in Renode or QEMU, as the emulation choice says.
- Install probe-rs from the `probe-rs-tools` crate. On 2026-10-22 the newest were probe-rs 0.32.0, defmt 1.2.0, and embedded-hal 1.0.0.

## What the gate runs

One `tests` entry builds the firmware for its target with the locked dependencies. The host tests and the emulation run come from their own standards.
