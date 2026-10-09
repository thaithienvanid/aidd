+++
id = "dotnet/archunitnet"
type = "opinionated"
fills = ["modular-monolith:module-boundaries"]
default = true
implements = "modular-monolith:Boundary check"
roles = ["architect", "developer", "reviewer"]
when_changed = ["**/*.cs", "**/*.csproj", "Directory.Packages.props", "*.slnx"]
why = "C# internal types already hide a module's code in its own project, and ArchUnitNET adds architecture rules as xUnit tests over the compiled assemblies, including a check for cycles between modules."
reviewed = "2026-10-09"
owner = "@thaithienvanid"
maturity = "emerging"
tool = { name = "archunitnet", registry = "github", package = "TNG/ArchUnitNET" }
version_policy = "current_stable"
checked_version = "0.13.4"
checked = "2026-10-09"
checked_by = "agent:claude-code/claude-opus-5-5"
source = "https://github.com/TNG/ArchUnitNET"
evidence = "PS> Install-Package TngTech.ArchUnitNET.xUnitV3"
pin = "0.13.4"
alternatives = ["NetArchTest.Rules (no release since 2021)", "a reflection test in xUnit"]
status = "active"
enforced_by = [
  { name = "boundaries", command = ["dotnet", "test", "--configuration", "Release", "--filter-trait", "Category=Architecture"] },
]
+++

# ArchUnitNET checks the .NET module boundaries

It answers the module-boundaries choice of `aidd-team:modular-monolith` for .NET. ArchUnitNET is under the Apache License 2.0.

ArchUnitNET is still 0.x, so its API can change in a minor release, and .NET has no mature alternative. Review this choice every 90 days. Its version comes from GitHub releases. NuGet's feed also holds a `2.1.0-draft` build, which NuGet marks as unlisted and which is not a release.

## What the team does

- Make each module its own project. Mark every type outside the module's API `internal`. Give `InternalsVisibleTo` only to the module's own test project.
- Add `TngTech.ArchUnitNET.xUnitV3` at `pin` in `Directory.Packages.props`, for `dotnet/xunit-v3`.
- Write one test class, `ArchitectureTests`, with `[Trait("Category", "Architecture")]`. Load every module's assembly once with `ArchLoader`.
- Check `Slices().Matching("<App>.Modules.(*)").Should().BeFreeOfCycles()`, so no cycle between modules passes.
- Write one rule for each dependency rule of the skill, such as "no type outside a module depends on its `Internal` namespace".
- List each known violation in the test as an exception, with its reason. That list is the violations baseline. It only gets shorter.

## What the gate runs

One `[[tests]]` entry runs the tests with the `Architecture` trait in Release. A broken rule fails the change.
