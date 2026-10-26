---
id: typescript/vitest-bench
type: opinionated
fills: [performance:benchmark-tool]
default: true
implements: performance:Regression guard
roles: [developer, verifier, reviewer]
when_changed: ["**/*.bench.ts", "**/*.benchmark.ts", vitest.config.ts]
why: "Vitest runs benchmarks with the same runner and transform as the tests, and its matchers fail a benchmark that is slower than another by more than a set margin. Its benchmark API is still experimental."
reviewed: "2026-10-22"
maturity: emerging
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
source: https://vitest.dev/guide/benchmarking.html
evidence: "Vitest lets you write benchmarks alongside your tests using the bench fixture from the test context."
alternatives: [tinybench, mitata, hyperfine for a whole program]
status: active
---

# Vitest benchmarks the TypeScript code

It answers the benchmark-tool choice of `aidd-team:performance` for TypeScript, with `typescript/vitest-tests`, which owns the Vitest pin.

Vitest 5 rewrote the benchmark API, and the docs still mark `bench` experimental. So this choice is reviewed every 90 days.

## What the team does

- Name each benchmark file `*.bench.ts`. Vitest runs those files only under `vitest bench`, so the unit run stays fast.
- Write each benchmark with the `bench` fixture inside a `test()`, and compare two implementations with `bench.compare()`, which interleaves their iterations.
- Fail on a regression with `toBeSlowerThan` or `toBeFasterThan` and a `delta`, such as `0.1`, so noise inside the margin passes.
- For a baseline, write the base's result with `writeResult` on the CI runner, and read it back with `bench.from()` in the head's run on that runner. Never regenerate it on a laptop.
- Pin `vite` and the Node.js version, so the base and the head run the same transform and engine.

## What the gate runs

No `tests` entry of its own. The Regression guard of `aidd-team:performance` runs `vitest bench` when a Spec sets a budget.
