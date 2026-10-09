+++
id = "dotnet/dotnet-lts"
type = "opinionated"
fills = ["ci-pipeline:language-version"]
default = true
implements = "ci-pipeline:Dev/prod parity"
roles = ["developer", "platform-engineer", "reviewer"]
when_changed = ["global.json", "**/*.csproj", "Directory.Build.props", "Dockerfile", "**/Dockerfile"]
why = "An LTS release of .NET is patched for three years, and global.json pins its SDK, so CI, each machine, and the image build with the same toolset and run on the same runtime."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "dotnet", registry = "dotnet", package = "sdk" }
version_policy = "latest_lts"
checked_version = "10.0.401"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
pin = "10.0.401"
source = "https://dotnetcli.blob.core.windows.net/dotnet/release-metadata/releases-index.json"
evidence = "\"latest-runtime\": \"10.0.12\", \"latest-sdk\": \"10.0.401\", \"product\": \".NET\", \"support-phase\": \"active\", \"release-type\": \"lts\","
alternatives = ["the current STS release"]
status = "active"
enforced_by = [
  { name = "sdk", command = ["dotnet", "--version"] },
]
+++

# The project targets the newest .NET LTS release

It answers the language-version choice of `aidd-team:ci-pipeline`.

## What the team does

- Commit a `global.json` at the repository's root that names the SDK in `pin`, with `"rollForward": "latestPatch"`, so a newer patch of that feature band still works. A new feature band brings new analyzer rules, so it moves in a change of its own.
- Set `<TargetFramework>` to the same release in `Directory.Build.props`, once for every project.
- Build the runtime image from the ASP.NET Core or runtime image of that release.
- Take each monthly patch. Move to the next LTS release in a change of its own; an STS release is not adopted.

## What the gate runs

One `[[tests]]` entry runs `dotnet --version`. When no installed SDK satisfies `global.json`, it fails the change.
