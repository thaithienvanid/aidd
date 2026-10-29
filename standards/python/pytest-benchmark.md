---
id: python/pytest-benchmark
type: opinionated
fills: [performance:benchmark-tool]
default: true
implements: performance:Regression guard
roles: [developer, verifier, reviewer]
when_changed: ["**/*.py", pyproject.toml]
why: "pytest-benchmark is a pytest fixture, so a benchmark sits beside the tests, calibrates its own rounds, and can fail the run when a saved baseline is beaten by a set margin. It is under BSD-2-Clause."
reviewed: "2026-10-22"
maturity: established
tool:
  name: pytest-benchmark
  registry: pypi
  package: pytest-benchmark
version_policy: current_stable
checked_version: "5.3.0"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "5.3.0"
source: https://pypi.org/pypi/pytest-benchmark/5.3.0/json
evidence: "\"version\":\"5.3.0\""
alternatives: [pyperf, hyperfine for a whole program]
status: active
---

# pytest-benchmark runs the Python benchmarks

It answers the benchmark-tool choice of `aidd-team:performance` for Python, with `python/pytest-tests`.

## What the team does

- Add `pytest-benchmark` at `pin` as a dev dependency, and write each benchmark as a test that takes the `benchmark` fixture.
- Put `--benchmark-disable` in `addopts`. The unit run then calls each benchmarked function once, as a plain test, with no timing.
- In the Regression guard, run the base in a second worktree with `--benchmark-enable --benchmark-only --benchmark-save=base` and a shared `--benchmark-storage`. Then run the head on the same runner, with that storage and `--benchmark-compare`, which reads the latest saved run.
- Fail the guard with `--benchmark-compare-fail=median:10%`, or the bound the Spec sets. The median resists one slow round better than the mean.
- Keep `.benchmarks/` out of the repository. A saved run from a laptop or another runner is never the baseline.

## What the gate runs

No `tests` entry of its own. The unit run of `python/pytest-tests` checks that each benchmark still runs, and the Regression guard compares the timings.
