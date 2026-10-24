---
id: go/govulncheck
type: opinionated
fills: [ci-pipeline:dependency-audit]
default: true
implements: enterprise-controls:Dependency scan
roles: [developer, security-engineer, reviewer]
when_changed: ["**/*.go", go.mod, go.sum]
why: "govulncheck reads the Go vulnerability database and reports only the vulnerable functions the code can reach, including those in the Go standard library, so its findings are few and real."
reviewed: "2026-10-16"
maturity: established
tool:
  name: govulncheck
  registry: go
  package: golang.org/x/vuln
version_policy: current_stable
checked_version: v1.8.0
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
pin: v1.8.0
source: https://pkg.go.dev/golang.org/x/vuln/cmd/govulncheck
evidence: Govulncheck reports known vulnerabilities that affect Go code. It uses static analysis of source code or a binary's symbol table to narrow down reports to only those that could affect the application.
alternatives: [OSV-Scanner alone]
status: active
enforced_by:
  - name: vulns
    command: [go, run, golang.org/x/vuln/cmd/govulncheck@v1.8.0, "./..."]
---

# govulncheck adds Go's own audit to the dependency scan

It answers the dependency-audit choice of `aidd-team:ci-pipeline` for Go.

## What the team does

- Keep the Dependency scan of `aidd-team:enterprise-controls`: OSV-Scanner still reads `go.sum` with every other lockfile. govulncheck is the Go addition, never its replacement.
- Fix a reachable finding by moving the module, or the Go toolchain for a standard-library one, to the fixed version.
- A finding that the code cannot reach still appears in OSV-Scanner's report and follows that scan's rules.
- Scan each release binary too, with `govulncheck -mode=binary`.

## What the gate runs

One `tests` entry runs govulncheck at `pin` over every package. It exits non-zero when the code reaches a known vulnerability.
