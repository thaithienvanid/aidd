+++
id = "go/depguard-boundaries"
type = "opinionated"
fills = ["modular-monolith:module-boundaries"]
default = true
implements = "modular-monolith:Boundary check"
roles = ["architect", "developer", "reviewer"]
when_changed = ["**/*.go", "go.mod", "boundaries-baseline.golangci.yml"]
why = "The Go compiler already hides each module's internal/ packages, and depguard in golangci-lint adds an allowlist of the imports each module may make, so the check needs no new tool."
reviewed = "2026-10-09"
owner = "@thaithienvanid"
maturity = "established"
checked = "2026-10-09"
checked_by = "agent:claude-code/claude-opus-5-5"
source = "https://pkg.go.dev/cmd/go"
evidence = "Code in or below a directory named \"internal\" is importable only by code that shares the same import path above the internal directory."
alternatives = ["go-arch-lint"]
status = "active"
enforced_by = [
  { name = "boundaries", command = ["golangci-lint", "run", "--config", "boundaries-baseline.golangci.yml", "./..."] },
]
+++

# internal/ and depguard check the Go module boundaries

It answers the module-boundaries choice of `aidd-team:modular-monolith` for Go. Its tool is golangci-lint, which `go/golangci-lint` pins and installs. golangci-lint is GPL-3.0. That licence covers the tool, not the code that it checks.

## What the team does

- Put each module's private code under `modules/<name>/internal/`. Then the compiler refuses an import of it from another module.
- Write the boundary rules in their own file, `boundaries-baseline.golangci.yml`, not in `.golangci.yml`. Set `linters.default: none`, and enable only `depguard`.
- Write one `depguard` rule for each module, with `list-mode: lax`. Its `files` match the module's folder. Its `deny` names the module path's `modules/` prefix. Its `allow` names the module itself and each `modules/<other>/api` it may import.
- Write one more rule: code under `packages/` imports no module and no app.
- With no rule, depguard allows only the standard library. Keep a rule for every module.
- The file is the violations baseline, so the gate routes each change to it as major (`baseline:module-boundaries`). A change that adds an `allow` entry needs an ADR.

## Cycles

Go refuses a cycle between packages only. Neither depguard nor go-arch-lint finds a cycle between modules, such as `orders/internal` to `billing/api` and `billing/internal` to `orders/api`. So a reviewer keeps the `allow` lists acyclic: draw the module graph from them, and refuse an entry that closes a loop.

## What the gate runs

One `[[tests]]` entry runs golangci-lint with `boundaries-baseline.golangci.yml` over every package. An import that a module's rule denies fails the change, and so does an import of another module's `internal/`.
