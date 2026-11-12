---
id: go/go-arch-lint
type: opinionated
fills: [modular-monolith:module-boundaries]
default: false
implements: modular-monolith:Boundary check
roles: [architect, developer, reviewer]
when_changed: ["**/*.go", go.mod, ".go-arch-lint.yml"]
why: "go-arch-lint maps packages to named components and checks every import against each component's mayDependOn list, so the allowed module graph lives in one file."
maturity: emerging
tool:
  name: go-arch-lint
  registry: goproxy
  package: github.com/fe3dback/go-arch-lint
version_policy: current_stable
checked_version: v1.19.0
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
citation:
  url: https://github.com/fe3dback/go-arch-lint
  quote: Linter used to enforce some good project structure and validate top level architecture (code layers)
alternatives: [internal/ with depguard in golangci-lint]
status: active
lock_command: [go, get, -tool, github.com/fe3dback/go-arch-lint]
enforced_by:
  - name: boundaries
    command: [go, tool, go-arch-lint, check]
---

# go-arch-lint checks the Go module boundaries

It answers the module-boundaries choice of `aidd-team:modular-monolith` for Go. go-arch-lint is MIT, and it needs Go 1.25 or later. `go/depguard-boundaries` stays the default.

## What the team does

- Keep each module's private code under `modules/<name>/internal/`, so the compiler still guards it.
- Write `.go-arch-lint.yml` at the root. Map each module's `api` and `internal` packages to components, and each folder under `packages/` to a common component.
- Give each component a `mayDependOn` list: its own packages and the `api` components it may import.
- Treat the file as the violations baseline. A change that widens a `mayDependOn` list needs an ADR.
- Like depguard, go-arch-lint finds no cycle between modules. A reviewer keeps the `mayDependOn` graph acyclic.

## What the tests run

One `tests` entry runs `go-arch-lint check` through `go tool`, at the version `go.mod` locks, so no binary is installed. Add it once with `go get -tool github.com/fe3dback/go-arch-lint`. It exits 1 when it finds an import that a component may not make, and that fails the change.
