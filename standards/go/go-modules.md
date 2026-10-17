---
id: go/go-modules
type: opinionated
fills: [ci-pipeline:package-manager]
default: true
implements: ci-pipeline:Dependencies declared and locked
roles: [developer, platform-engineer, reviewer]
when_changed: [go.mod, go.sum, "**/*.go"]
why: "Go modules are built into the go command: go.mod declares each requirement, go.sum records each hash, and the checksum database confirms them, so no second tool is needed."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: "https://go.dev/ref/mod#go-mod-tidy"
evidence: The -diff flag causes go mod tidy not to modify go.mod or go.sum but instead print the necessary changes as a unified diff. It exits with a non-zero code if the diff is not empty.
alternatives: [Go modules with a committed vendor directory]
status: active
enforced_by:
  - name: tidy
    command: [go, mod, tidy, -diff]
  - name: verify
    command: [go, mod, verify]
---

# Go modules declare and lock the Go dependencies

It answers the package-manager choice of `aidd-team:ci-pipeline`. Its version is the Go toolchain's, which `go/go-version` pins.

## What the team does

- Commit `go.mod` and `go.sum`. Run `go mod tidy` before each commit that changes an import.
- Fetch private modules through `GOPRIVATE` and the team's proxy. A committed `replace` never points at a local path.
- Upgrade with `go get module@version` in a change of its own.

## What the gate runs

Two `tests` entries. `go mod tidy -diff` fails when `go.mod` or `go.sum` is out of date with the imports. `go mod verify` fails when a module in the cache no longer matches its recorded hash.
