---
id: go/go-version
type: opinionated
fills: [ci-pipeline:language-version]
default: true
implements: ci-pipeline:Dependencies declared and locked
roles: [developer, platform-engineer, reviewer]
when_changed: [go.mod, "**/*.go"]
why: "The Go team supports each major release until two newer ones ship, and go.mod can name both the oldest supported language version and the exact toolchain, so one file pins Go everywhere."
reviewed: "2026-10-16"
maturity: established
tool:
  name: go
  registry: go.dev
  package: go
version_policy: current_stable
checked_version: "1.27.1"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://go.dev/doc/devel/release
evidence: "go1.27.1 (released 2026-09-01) includes fixes to cgo, the compiler, the runtime, the go fix command, and the database/sql, debug/elf, encoding/json, net/http, os, simd, and simd/archsimd packages."
alternatives: [the previous supported Go release]
status: active
enforced_by:
  - name: stdversion
    command: [go, vet, -stdversion, "./..."]
---

# go.mod pins the Go version

It answers the language-version choice of `aidd-team:ci-pipeline`. The newest Go release was read at go.dev on the `checked` day; `evidence` quotes it.

## What the team does

- The `go` line in `go.mod` states the oldest Go release the module builds with. Keep it at a release the Go team still supports.
- The `toolchain` line names the exact release the team builds with: the newest patch of the current major. With `GOTOOLCHAIN=auto`, the default, a machine whose own Go is older than that line downloads and runs it; a newer local Go builds as it is.
- CI reads the version from `go.mod` (for example `go-version-file: go.mod` in `actions/setup-go`), never from a second copy.
- Move to a new major through `aidd-team:dependency-upgrade`, before the old one leaves support.

## What the gate runs

One `tests` entry runs `go vet -stdversion ./...`. It reports any standard-library symbol newer than the `go` line, so the stated minimum stays true.
