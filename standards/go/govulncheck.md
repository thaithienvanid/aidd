---
id: go/govulncheck
type: opinionated
fills: [ci-pipeline:dependency-audit]
default: true
implements: enterprise-controls:Dependency scan
roles: [developer, security-engineer, reviewer]
when_changed: ["**/*.go", go.mod, go.sum]
why: "govulncheck reads the Go vulnerability database and reports only the vulnerable functions the code can reach, including those in the Go standard library, so its findings are few and real."
maturity: established
tool:
  name: govulncheck
  registry: goproxy
  package: golang.org/x/vuln
version_policy: current_stable
checked_version: v1.8.0
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
citation:
  url: https://pkg.go.dev/golang.org/x/vuln/cmd/govulncheck
  quote: Govulncheck reports known vulnerabilities that affect Go code. It uses static analysis of source code or a binary's symbol table to narrow down reports to only those that could affect the application.
alternatives: [OSV-Scanner alone]
status: active
lock_command: [go, get, -tool, golang.org/x/vuln/cmd/govulncheck]
enforced_by:
  - name: vulns
    command: [go, tool, govulncheck, "./..."]
---

# govulncheck adds Go's own audit to the dependency scan

It answers the dependency-audit choice of `aidd-team:ci-pipeline` for Go.

## What the team does

- Keep the Dependency scan of `aidd-packs:enterprise-controls`: OSV-Scanner still reads `go.sum` with every other lockfile. govulncheck is the Go addition, never its replacement.
- Fix a reachable finding by moving the module, or the Go toolchain for a standard-library one, to the fixed version.
- A finding that the code cannot reach still appears in OSV-Scanner's report and follows that scan's rules.
- Scan each release binary too, with `govulncheck -mode=binary`.

## What the tests run

One `tests` entry runs govulncheck through `go tool`, at the version `go.mod` locks, over every package. Add it once with `go get -tool golang.org/x/vuln/cmd/govulncheck`. It exits non-zero when the code reaches a known vulnerability.
