---
id: go/go-test-race
type: opinionated
fills: [ci-pipeline:test-runner]
default: true
implements: test-design:Flake check
roles: [developer, tester, reviewer]
when_changed: ["**/*.go", go.mod, go.sum, "**/testdata/**"]
why: "go test ships with the toolchain, and the race detector turns a data race, one of the hardest concurrency bugs to debug, into a test failure that names both goroutines."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://go.dev/doc/articles/race_detector
evidence: Data races are among the most common and hardest to debug types of bugs in concurrent systems.
alternatives: [gotestsum, Ginkgo]
status: active
enforced_by:
  - name: test
    command: [go, test, -race, -count=1, "./..."]
---

# go test runs the Go tests with the race detector on

It answers the test-runner choice of `aidd-team:ci-pipeline`. Its version is the Go toolchain's, which `go/go-version` pins.

## What the team does

- Keep tests beside the code in `_test.go` files, as table-driven tests with `t.Run` subtests.
- Call `t.Parallel()` in tests that share no state, so the race detector sees real concurrency.
- Pass `-count=1` in CI, so a cached result never stands in for a run.
- Rerun only what the change touched, as a CI step beside the gate: list the `.go` files in `git diff --name-only <base>...HEAD`, take their directories, and run `go test -race -count=20` on those packages. 20 is the team's rerun count; set it once in the CI file. The Go tool has no flag that selects changed packages, so this step is not a `tests` entry.
- The race detector needs cgo: keep `CGO_ENABLED=1` in the test job, with a C compiler on the runner (macOS excepted).
- A `//go:build !race` exclusion names the issue that tracks the race it hides.

## What the gate runs

One `tests` entry runs `go test -race -count=1 ./...`: every test once, over the whole module. A failing test or a reported data race fails the change.
