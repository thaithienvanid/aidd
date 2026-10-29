---
id: dotnet/benchmarkdotnet
type: opinionated
fills: [performance:benchmark-tool]
default: true
implements: performance:Regression guard
roles: [developer, verifier, reviewer]
when_changed: ["benchmarks/**", Directory.Packages.props]
why: "BenchmarkDotNet runs .NET benchmarks in a separate process for each one, with warmup, pilot, and outlier handling, and exports full results for a statistical comparison. The .NET Foundation hosts it under MIT."
reviewed: "2026-10-22"
maturity: established
tool:
  name: benchmarkdotnet
  registry: nuget
  package: BenchmarkDotNet
version_policy: current_stable
checked_version: "0.15.8"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "0.15.8"
source: https://api.nuget.org/v3-flatcontainer/benchmarkdotnet/index.json
evidence: "\"0.15.8\""
alternatives: [hyperfine for a whole program]
status: active
enforced_by:
  - name: bench
    command: [dotnet, run, -c, Release, --project, benchmarks, --, --job, Dry, --filter, "*"]
---

# BenchmarkDotNet benchmarks the .NET code

It answers the benchmark-tool choice of `aidd-team:performance` for .NET. BenchmarkDotNet is still 0.x, but the .NET runtime team measures its own code with it.

## What the team does

- Keep the benchmarks in a console project, `benchmarks/`, with `BenchmarkDotNet` at `pin` in `Directory.Packages.props`. Its `Main` calls `BenchmarkSwitcher`, so the command-line options work.
- Always run a Release build, and add `[MemoryDiagnoser]` where allocations matter.
- In the Regression guard, run the base's and the head's builds on the same runner, each with `--exporters json`.
- Compare the two sets of `*-full.json` results with the .NET team's ResultsComparer, `--threshold` set to the Spec's bound. It reports a benchmark as slower only when a statistical test agrees.
- Never compare with results exported on another machine or another runtime.

## What the gate runs

One `bench` test runs every benchmark once with the `Dry` job, as a check and not a measurement. A benchmark that no longer builds or throws fails the change.
