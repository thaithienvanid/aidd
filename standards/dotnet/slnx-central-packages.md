---
id: dotnet/slnx-central-packages
type: opinionated
fills: [ci-pipeline:workspace]
default: true
implements: ci-pipeline:Dependencies declared and locked
roles: [developer, sre, reviewer]
when_changed: ["*.slnx", "**/*.csproj", Directory.Build.props, Directory.Packages.props]
why: "One .slnx solution lists every project, and Directory.Build.props and Directory.Packages.props give all of them one set of build settings and package versions."
reviewed: "2026-10-16"
maturity: emerging
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
source: https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-new-sdk-templates
evidence: "Starting with .NET 10, the default format is slnx."
alternatives: [a .sln solution file]
status: active
enforced_by:
  - name: members
    command:
      - sh
      - -c
      - "set -eu; sln=$(git ls-files -- '*.slnx'); n=$(printf '%s' \"$sln\" | awk 'END {print NR}'); if [ \"$n\" -ne 1 ] || [ \"${sln#*/}\" != \"$sln\" ]; then echo \"want one .slnx at the repository root; found: ${sln:-none}\"; exit 1; fi; missing=$(git ls-files -- '*.csproj' | while IFS= read -r p; do tr '\\\\' '/' < \"$sln\" | grep -qF \"\\\"$p\\\"\" || echo \"$p\"; done); test -z \"$missing\" || {printf 'not in %s:\\n%s\\n' \"$sln\" \"$missing\"; exit 1;}"
---

# One .slnx solution holds the .NET apps, modules, and packages

It answers the workspace choice of `aidd-team:ci-pipeline` for .NET. Its tool is the .NET SDK, which `dotnet/dotnet-lts` pins. The SDK is MIT. The package versions come from `dotnet/central-package-management`.

## What the team does

- Keep one `.slnx` file at the repository root. On the .NET 10 SDK, `dotnet new sln` writes one. `dotnet sln migrate` turns an old `.sln` into it.
- Add each project with `dotnet sln add`: the apps, one project for each module, and the shared packages.
- Put the settings that every project shares, such as `Nullable` and `TreatWarningsAsErrors`, in one `Directory.Build.props` at the root.
- Refer to a sibling project with `<ProjectReference>`, never to its built DLL.

## What the gate runs

One `tests` entry fails when git tracks no `.slnx` file at the root, or more than one, or a `.csproj` that the solution does not list. A project outside the solution would never build or test in CI.
