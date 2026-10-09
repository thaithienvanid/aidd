+++
id = "dotnet/minimal-apis"
type = "opinionated"
fills = ["apis-and-services:api-framework"]
default = true
implements = "apis-and-services:Schema conformance"
roles = ["architect", "developer", "reviewer"]
when_changed = ["**/*.cs", "**/*.csproj", "openapi.json", "openapi.yaml"]
why = "Minimal APIs are ASP.NET Core's recommended way to build HTTP APIs, with built-in OpenAPI generation, so the service and its contract come from one code base."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "aspnetcore-openapi", registry = "nuget", package = "Microsoft.AspNetCore.OpenApi" }
version_policy = "latest_lts"
checked_version = "10.0.12"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
pin = "10.0.12"
source = "https://learn.microsoft.com/en-us/aspnet/core/fundamentals/apis"
evidence = "For new projects, we recommend using Minimal APIs as they provide a simplified, high-performance approach for building APIs with minimal code and configuration."
alternatives = ["ASP.NET Core controllers", "FastEndpoints"]
status = "active"
enforced_by = [
  { name = "contract", command = ["dotnet", "test", "--configuration", "Release", "--filter-trait", "Category=Contract"] },
]
+++

# ASP.NET Core minimal APIs serve the .NET API

It answers the api-framework choice of `aidd-team:apis-and-services`.

## What the team does

- Map the endpoints in route groups (`MapGroup`), one group per resource, each with its tags and its authorization policy.
- Return `TypedResults`, so each endpoint's responses reach the OpenAPI document.
- Reference `Microsoft.AspNetCore.OpenApi` at the version in `pin`, and write the document at build time with `Microsoft.Extensions.ApiDescription.Server`. Diff it against the contract.
- Validate each request at the boundary, and answer a bad one with `ProblemDetails`.
- Bind settings with the options pattern, from the environment.

## What the gate runs

One `[[tests]]` entry runs the tests with the trait `Category=Contract`: they start the service with `WebApplicationFactory<Program>`, call each operation of the committed OpenAPI document, and validate each response against it. A response the contract does not allow fails the change.
