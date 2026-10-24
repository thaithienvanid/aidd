---
id: dotnet/dotnet-format
type: opinionated
fills: [ci-pipeline:formatter]
default: true
implements: product-defaults:dev_basics
roles: [developer, reviewer]
when_changed: ["**/*.cs", "**/.editorconfig", "**/*.csproj"]
why: "dotnet format ships with the .NET SDK and reads the rules from .editorconfig, so CI, the pre-commit hook, and every editor lay out C# the same way with no extra tool."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-format
evidence: dotnet format is a code formatter that applies style preferences and static analysis recommendations to a project or solution.
alternatives: [CSharpier]
status: active
enforced_by:
  - name: format
    command: [dotnet, format, --verify-no-changes]
---

# dotnet format formats the C# code

It answers the formatter choice of `aidd-team:ci-pipeline`.

## What the team does

- Keep one `.editorconfig` at the repository's root, with the layout and the naming rules. Commit it.
- Run the `dotnet format` of the SDK that `global.json` selects, so its version moves only with the SDK (`dotnet/dotnet-lts`).
- Set the severity of each style rule in `.editorconfig`, so the check and the editor agree.
- Run `dotnet format` before you commit, or from the pre-commit hook.

## What the gate runs

One `tests` entry runs `dotnet format --verify-no-changes`. A file it would change fails the change.
