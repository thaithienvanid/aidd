---
id: go/benchstat
type: opinionated
fills: [performance:benchmark-tool]
default: true
implements: performance:Regression guard
roles: [developer, verifier, reviewer]
when_changed: ["**/*_test.go", go.mod]
why: "Go's own testing.B runs the benchmarks with no extra library, and benchstat from the Go team compares two sets of runs and reports a change only when it is statistically significant."
reviewed: "2026-10-22"
maturity: established
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
source: https://pkg.go.dev/golang.org/x/perf/cmd/benchstat
evidence: Each benchmark should be run at least 10 times to gather a statistically significant sample of results.
alternatives: [hyperfine for a whole program]
status: active
enforced_by:
  - name: bench
    command: [go, test, "-run=^$", "-bench=.", "-benchtime=1x", "./..."]
---

# testing.B and benchstat benchmark the Go code

It answers the benchmark-tool choice of `aidd-team:performance` for Go. benchstat is under the Go project's BSD-3-Clause license.

`golang.org/x/perf` publishes no tagged release, only pseudo-versions. So `go.mod` locks benchstat, not a `pin` here.

## What the team does

- Write each benchmark as a `BenchmarkXxx(b *testing.B)` function with a `for b.Loop()` body, and call `b.ReportAllocs()` where allocations matter.
- Add benchstat as a tool of the module, with `go get -tool golang.org/x/perf/cmd/benchstat`, and run it as `go tool benchstat`.
- In the Regression guard, run `go test -run='^$' -bench=. -count=10` on the base and then on the head, on the same runner, into `old.txt` and `new.txt`.
- Run `benchstat old.txt new.txt`. A change marked `~` is noise. Fail the guard only on a significant slowdown, with `p` under 0.05, past the Spec's bound.
- Keep the runner otherwise idle during the two runs, and never mix results from two machines.

## What the gate runs

One `bench` test runs every benchmark once (`-benchtime=1x`), so a benchmark that no longer builds or panics fails the change. It times nothing; the Regression guard does.
