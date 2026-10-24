---
id: rust/clap
type: opinionated
fills: [api-design:cli-framework]
default: true
implements: api-design:Implement
roles: [architect, developer, reviewer]
when_changed: ["**/*.rs", Cargo.toml, "**/Cargo.toml", Cargo.lock]
why: "clap is the common Rust argument parser: one derived struct gives the parsing, the help, the errors, and the shell completions, so the flags a person types are typed and checked."
reviewed: "2026-10-22"
maturity: established
tool:
  name: clap
  registry: crates
  package: clap
version_policy: current_stable
checked_version: "4.6.7"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "4"
source: https://github.com/clap-rs/clap
evidence: "Create your command-line parser, with all of the bells and whistles, declaratively or procedurally."
alternatives: [argh, lexopt, bpaf]
status: active
enforced_by:
  - name: clap-major
    command: [cargo, tree, --locked, --invert, clap@4]
---

# clap parses the arguments of a Rust command-line tool

It answers the cli-framework choice of `aidd-team:api-design`. clap is MIT or Apache-2.0, at the user's choice.

## What the team does

- Use the derive API: `#[derive(Parser)]` on one `Cli` struct, with a `Subcommand` enum for each verb. Turn on the `derive` feature only, plus `env` when a flag may come from the environment.
- Keep the binary thin. `main` parses, then calls the library crate, so the tests reach the logic without a process.
- Add a unit test that calls `Cli::command().debug_assert()`. It catches a broken definition, such as two flags with one name, before a person does.
- Treat the flags, the subcommands, and the exit codes as the tool's public contract. Removing or renaming one is a breaking change.
- Return a nonzero exit code on every failure, and write errors to standard error, never standard output.
- Generate the shell completions with `clap_complete` at build or release time, never by hand.

## What the gate runs

One `tests` entry runs `cargo tree --invert` on `Cargo.lock`. It fails when the lockfile no longer holds clap 4, the major this standard was checked at, so a new major brings an updated standard.
