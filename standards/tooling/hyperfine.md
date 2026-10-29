---
id: tooling/hyperfine
type: opinionated
fills: [performance:benchmark-tool]
default: true
implements: performance:Regression guard
roles: [developer, verifier, reviewer]
when_changed: ["bench/**"]
why: "hyperfine times any command-line program over many runs, with warmup and outlier detection, and times two builds in one run, so both are measured on one machine. It is dual-licensed under MIT and Apache-2.0."
reviewed: "2026-10-22"
maturity: established
tool:
  name: hyperfine
  registry: github
  package: sharkdp/hyperfine
version_policy: current_stable
checked_version: "2.0.0"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "2.0.0"
source: https://api.github.com/repos/sharkdp/hyperfine/releases/tags/v2.0.0
evidence: "\"tag_name\": \"v2.0.0\""
alternatives: [the language's own benchmark harness]
status: active
---

# hyperfine benchmarks a command-line program

It answers the benchmark-tool choice of `aidd-team:performance` for a whole program, in any language. Use the ecosystem's own harness for a function inside it.

hyperfine 2.0.0 changed the defaults. It runs each command without a shell, so use `-S` for shell syntax. Its JSON export is now schema version 2.

## What the team does

- Install hyperfine at `pin` in CI, and keep the benchmark's inputs and its script in `bench/`.
- Build the base and the head, then time both in one run: `hyperfine --warmup 3 --runs 20 'base/app <args>' 'head/app <args>'`. The first command is the reference, and hyperfine reports the change of the second against it.
- Export the run with `--export-json` and keep it as the evidence.
- Fail the guard when the head is slower than the Spec's bound and Welch's t-test on the two runs, from hyperfine's `scripts/welch_ttest.py`, says the difference is real.
- Never compare with a number timed on another machine.

## What the gate runs

No `tests` entry of its own. The Regression guard of `aidd-team:performance` runs the comparison when a Spec sets a budget.
