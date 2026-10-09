+++
id = "rust/cargo-nextest"
type = "opinionated"
fills = ["ci-pipeline:test-runner"]
default = true
implements = "test-design:Flake check"
roles = ["developer", "tester", "reviewer"]
when_changed = ["**/*.rs", "Cargo.toml", "**/Cargo.toml", "Cargo.lock", ".config/nextest.toml"]
why = "cargo-nextest runs each test in its own process and in parallel, so a test cannot leak state into another, and a slow or hung test is named and stopped."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "cargo-nextest", registry = "crates", package = "cargo-nextest" }
version_policy = "current_stable"
checked_version = "0.9.146"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
pin = "0.9.146"
source = "https://nexte.st/docs/running/"
evidence = "Doctests are currently not supported because of limitations in stable Rust."
alternatives = ["cargo test"]
status = "active"
enforced_by = [
  { name = "test", command = ["cargo", "nextest", "run", "--workspace", "--locked", "--no-tests=fail"] },
  { name = "doctest", command = ["cargo", "test", "--doc", "--workspace", "--locked"] },
]
+++

# cargo-nextest runs the Rust tests

It answers the test-runner choice of `aidd-team:ci-pipeline`.

## What the team does

- Put `nextest-version = { required = "<pin>" }` at the top of `.config/nextest.toml`, so an older nextest refuses to run.
- Install the pre-built binary at `pin` in CI, for example with `taiki-e/install-action`.
- Keep the service's logic in a library crate (`src/lib.rs`, with a thin `main.rs`), so it has doctests and unit tests to run; `cargo test --doc` fails on a package with no library target.
- Test with the default features. Add `--all-features` only when every feature is additive.
- Keep `retries` at zero in the CI profile. A test that passes only on a second try gets fixed, not retried.
- Rerun only what the change touched, as a CI step beside the gate: `cargo nextest run --stress-count=20 -E 'rdeps(<crate>)'` for each crate the diff changes. 20 is the team's rerun count. The step needs the diff, so it is not a `[[tests]]` entry.
- Set `slow-timeout` with `terminate-after`, so a hung test fails instead of stalling the job.

## What the gate runs

Two `[[tests]]` entries: `cargo nextest run`, each test once over the workspace, and `cargo test --doc` for the doctests, which nextest does not run. A failure in either fails the change, and so does a workspace with no tests at all (`--no-tests=fail`, exit code 4).
