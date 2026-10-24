---
id: rust/cargo-semver-checks
type: opinionated
fills: [package-publishing:api-diff-tool]
default: true
implements: package-publishing:Public API diff
roles: [developer, reviewer]
when_changed: ["**/*.rs", Cargo.toml, "**/Cargo.toml", Cargo.lock]
why: "cargo-semver-checks compares the crate's public API, read from rustdoc's JSON, with its last release on crates.io, so a breaking change cannot ship under a minor or patch version."
reviewed: "2026-10-22"
maturity: established
tool:
  name: cargo-semver-checks
  registry: crates
  package: cargo-semver-checks
version_policy: current_stable
checked_version: "0.51.0"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "0.51.0"
source: https://github.com/obi1kenobi/cargo-semver-checks
evidence: "By default, cargo-semver-checks uses crates.io to look up the previous version of the crate, which is used as the baseline for semver-checking the current version of the crate."
alternatives: [cargo-public-api, a hand-kept API report]
status: active
enforced_by:
  - name: semver
    command: [cargo, semver-checks, --workspace]
  - name: docs
    command: [cargo, doc, --workspace, --no-deps, --locked, --config, "build.rustdocflags=[\"-D\", \"warnings\"]"]
---

# cargo-semver-checks keeps a Rust library's public API to its version

It answers the api-diff-tool choice of `aidd-team:package-publishing` for a crate published on crates.io. cargo-semver-checks is MIT or Apache-2.0, at the user's choice.

## What the team does

- Install it at `pin` in CI, with `cargo install --locked` or the pre-built binary.
- Move the pin with each toolchain upgrade of `rust/msrv`. It reads rustdoc's JSON, whose format changes between Rust releases, and each release of the tool supports the stable Rust of its day.
- Bump the version in `Cargo.toml` in the same change as the break it allows. A major bump below 1.0 is the minor number, as Cargo reads it.
- Set `publish = false` on every crate that never goes to crates.io, so the check skips it.
- Adopt this standard with the first release: until a crate is on crates.io, the check has no baseline.
- The tool does not catch every break yet. A change to behaviour, not to a signature, still needs the reviewer's eye.
- Keep the pack's Publish dry run, `cargo publish --dry-run`, beside these checks.

## What the gate runs

Two `tests` entries. `cargo semver-checks` compares each publishable workspace crate with its newest release on crates.io. It exits with 100 on a break the version does not allow, and with 101 when it cannot finish. `cargo doc` builds the API docs that docs.rs will show, and a rustdoc warning, such as a broken link, fails it. Any failure fails the change.
