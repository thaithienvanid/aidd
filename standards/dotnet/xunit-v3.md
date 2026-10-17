---
id: dotnet/xunit-v3
type: opinionated
fills: [ci-pipeline:test-runner]
default: true
implements: product-defaults:dev_basics
roles: [developer, tester, reviewer]
when_changed: ["**/*.cs", "**/*.csproj", Directory.Packages.props]
why: xUnit.net v3 is the maintained line of .NET's common test framework; each test project is its own executable and runs on the Microsoft Testing Platform.
reviewed: "2026-10-16"
maturity: established
tool:
  name: xunit
  registry: nuget
  package: xunit.v3
version_policy: current_major
checked_version: "4.0.1"
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
pin: "4.0.1"
source: https://xunit.net/releases/v3/4.0.1
evidence: xUnit.net Core Framework v3 4.0.1
alternatives: [NUnit, MSTest, TUnit]
status: active
enforced_by:
  - name: test
    command: [dotnet, test, --configuration, Release]
---

# xUnit.net v3 runs the .NET tests

It answers the test-runner choice of `aidd-team:ci-pipeline`.

## What the team does

- Reference the `xunit.v3` package at the version in `pin`, from `Directory.Packages.props`. The v2 `xunit` package is in maintenance; do not start on it.
- On the .NET 10 SDK, run `dotnet test` on Microsoft Testing Platform: set `"test": {"runner": "Microsoft.Testing.Platform"}` in `global.json`. The 4.x packages use Microsoft Testing Platform v2, which no longer runs under the VSTest mode of `dotnet test` on that SDK. Keep `xunit.runner.visualstudio` and `Microsoft.NET.Test.Sdk` only for a tool that still needs VSTest.
- Keep the `xunit.analyzers` rules on, as errors.
- Use `[Theory]` with `[InlineData]` or `[MemberData]` for a table of cases.
- Share an expensive fixture through `IClassFixture` or an assembly fixture, never through a static field.
- Give a skipped test a reason that links its issue.

## What the gate runs

One `tests` entry runs `dotnet test` in Release. A failing test fails the change.
