---
id: dotnet/analyzers-nullable
type: opinionated
fills: [ci-pipeline:type-checker, ci-pipeline:linter]
default: true
implements: product-defaults:dev_basics
roles: [developer, reviewer]
when_changed: ["**/*.cs", "**/*.csproj", Directory.Build.props, "**/.editorconfig"]
why: "Nullable reference types make the C# compiler check null-safety, and the SDK's analyzers add quality rules in the same build; as errors, they are the language's own strict check."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://learn.microsoft.com/en-us/dotnet/fundamentals/code-analysis/overview
evidence: These analyzers are included with the .NET SDK and you don't need to install them separately.
alternatives: [SonarAnalyzer.CSharp, Roslynator]
status: active
enforced_by:
  - name: build
    command: [dotnet, build, --configuration, Release, -warnaserror]
---

# The C# compiler checks nulls and the analyzers in every build

It answers the type-checker and linter choices of `aidd-team:ci-pipeline`: nullable reference types check the types, and the code-quality and style analyzers lint.

## What the team does

- Set these in `Directory.Build.props`, once for every project: `<Nullable>enable</Nullable>`, `<AnalysisLevel>latest-recommended</AnalysisLevel>`, `<EnforceCodeStyleInBuild>true</EnforceCodeStyleInBuild>`, and `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>`.
- Never use the null-forgiving operator (`!`) without a comment that says why the value cannot be null.
- Turn off a rule in `.editorconfig`, with the reason beside it, never with `#pragma` alone.
- The analyzers come with the SDK that `global.json` selects, so a new SDK can add warnings: upgrade it in a change of its own.

## What the gate runs

One `tests` entry builds in Release with warnings as errors. A nullable warning or an analyzer finding fails the change.
