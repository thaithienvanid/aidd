---
id: go/testcontainers
type: opinionated
fills: [test-design:integration-test-services]
default: true
implements: test-design:Real throwaway dependencies
roles: [developer, tester, reviewer]
when_changed: ["**/*_test.go", go.mod, go.sum, "**/testdata/**"]
why: "Testcontainers for Go starts the real database and services from go test, one throwaway container each, and removes each container when its test ends."
reviewed: "2026-10-16"
maturity: established
tool:
  name: testcontainers-go
  registry: go
  package: github.com/testcontainers/testcontainers-go
version_policy: current_stable
checked_version: v0.44.0
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
pin: v0.44.0
source: https://golang.testcontainers.org/
evidence: Testcontainers for Go is a Go package that makes it simple to create and clean up container-based dependencies for automated integration/smoke tests.
alternatives: [Docker Compose started by the test run, the provider's local emulator]
status: active
enforced_by:
  - name: integration
    command: [go, test, -race, -count=1, -tags=integration, "./..."]
---

# Testcontainers starts the Go integration-test services

It answers the integration-test-services choice of `aidd-team:test-design`. Testcontainers for Go is under the MIT license. It is not yet at 1.0, so move to a new minor release in its own change.

## What the team does

- Require `github.com/testcontainers/testcontainers-go` at the version in `pin`, and the module for each service, such as `modules/postgres`, at the same version.
- Start each container with its module's `Run`, or `testcontainers.Run`, and call `testcontainers.CleanupContainer(t, c)` right after, so the container is removed when the test ends.
- Give each image its tag and digest, from the major release that production runs.
- Read the address from the container, such as the Postgres module's `ConnectionString`, never from a fixed host or port.
- Put each such test file behind `//go:build integration`, so `go test ./...` runs without Docker.

## What the gate runs

One `tests` entry runs `go test -race -count=1 -tags=integration ./...`: the unit tests and the integration tests together. A test that fails, or a container that never starts, fails the change.
