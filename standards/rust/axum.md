---
id: rust/axum
type: opinionated
fills: [apis-and-services:api-framework]
default: true
implements: product-defaults:operability
roles: [architect, developer, reviewer]
when_changed: ["**/*.rs", Cargo.toml, "**/Cargo.toml", Cargo.lock]
why: "axum, from the tokio project, routes requests to typed handlers and takes its middleware from tower, so timeouts, limits, and tracing come as shared layers on the tokio runtime."
reviewed: "2026-10-16"
maturity: established
tool:
  name: axum
  registry: crates
  package: axum
version_policy: current_stable
checked_version: "0.8.9"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
pin: "0.8"
source: https://github.com/tokio-rs/axum
evidence: axum is an HTTP routing and request-handling library that focuses on ergonomics and modularity.
alternatives: [actix-web, Rocket, Poem]
status: active
enforced_by:
  - name: axum-major
    command: [cargo, tree, --locked, --invert, axum@0.8]
---

# axum on tokio serves the Rust API

It answers the api-framework choice of `aidd-team:apis-and-services`.

## What the team does

- Start tokio's multi-threaded runtime with `#[tokio::main]`. Never block it: move blocking work to `tokio::task::spawn_blocking`. To find a task that stalls, run tokio-console against a local build with `tokio_unstable` and `console-subscriber`; never ship that build.
- Serve with `axum::serve`, and stop on SIGTERM with `with_graceful_shutdown`.
- Add timeouts, body limits, and tracing as `tower` and `tower-http` layers, not hand-written middleware.
- Take input through typed extractors such as `Json<T>`, `Path<T>`, and `Query<T>`. A rejection answers with a problem-details body.
- Share state through `State<T>`, never a global.

## What the gate runs

One `tests` entry runs `cargo tree --invert` on `Cargo.lock`. It fails when the lockfile no longer holds the axum release line this standard was checked at, so an upgrade past it brings an updated standard. tokio comes in through axum's default `tokio` feature.
