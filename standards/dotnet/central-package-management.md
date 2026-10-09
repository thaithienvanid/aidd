+++
id = "dotnet/central-package-management"
type = "opinionated"
fills = ["ci-pipeline:package-manager"]
default = true
implements = "ci-pipeline:Dependencies declared and locked"
roles = ["developer", "platform-engineer", "reviewer"]
when_changed = ["Directory.Packages.props", "**/*.csproj", "**/packages.lock.json", "nuget.config"]
why = "NuGet's Central Package Management keeps every package version in one file, and lock files with locked-mode restore make CI install exactly what was reviewed."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
source = "https://learn.microsoft.com/en-us/nuget/consume-packages/central-package-management"
evidence = "To get started with Central Package Management, create a Directory.Packages.props file at the root of your repository and set the MSBuild property ManagePackageVersionsCentrally to true."
alternatives = ["versions in each project file", "Paket"]
status = "active"
enforced_by = [
  { name = "lock", command = ["dotnet", "restore", "--locked-mode"] },
]
+++

# Central Package Management declares and locks the .NET packages

It answers the package-manager choice of `aidd-team:ci-pipeline`.

## What the team does

- Set `ManagePackageVersionsCentrally` in `Directory.Packages.props`, and give each package one `<PackageVersion>` there. A project's `<PackageReference>` has no version.
- Set `RestorePackagesWithLockFile` for every project, and commit each `packages.lock.json`.
- Name the package sources in a committed `nuget.config`, with package source mapping.
- Pin local tools, such as `dotnet-ef`, in `.config/dotnet-tools.json`, and run `dotnet tool restore` in CI.

## What the gate runs

One `[[tests]]` entry restores in locked mode. A lock file that no longer matches the declared versions fails the change.
