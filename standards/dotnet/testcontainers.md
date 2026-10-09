+++
id = "dotnet/testcontainers"
type = "opinionated"
fills = ["test-design:integration-test-services"]
default = true
implements = "test-design:Real throwaway dependencies"
roles = ["developer", "tester", "reviewer"]
when_changed = ["**/*Tests/**", "**/*Tests.csproj", "Directory.Packages.props"]
why = "Testcontainers for .NET starts the real database and services from the test run, one throwaway container each, and its modules give each service a ready connection string."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "testcontainers-dotnet", registry = "nuget", package = "Testcontainers" }
version_policy = "current_stable"
checked_version = "4.15.0"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
pin = "4.15.0"
source = "https://dotnet.testcontainers.org/"
evidence = "Testcontainers for .NET is a library to support tests with throwaway instances of Docker containers for all compatible .NET Standard versions."
alternatives = ["Docker Compose started by the test run", "the provider's local emulator", ".NET Aspire testing"]
status = "active"
enforced_by = [
  { name = "integration", command = ["dotnet", "test", "--configuration", "Release", "--filter-trait", "Category=Integration"] },
]
+++

# Testcontainers starts the .NET integration-test services

It answers the integration-test-services choice of `aidd-team:test-design`.

## What the team does

- Reference `Testcontainers` and the module for each service, such as `Testcontainers.PostgreSql`, at the version in `pin`, from `Directory.Packages.props`. Add `Testcontainers.XunitV3` for the xUnit.net v3 fixtures.
- Start a container in a class or assembly fixture, and dispose of it with the fixture.
- Pin each image by tag and digest, on the major release that production runs.
- Read the address from the container's connection string, never a fixed host or port.
- Mark each such test with the trait `Category=Integration`, so the unit tests run without Docker.

## What the gate runs

One `[[tests]]` entry runs the tests with the trait `Category=Integration`. A container that fails to start, or a failing test, fails the change.
