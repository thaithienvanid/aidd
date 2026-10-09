+++
id = "dotnet/ef-core"
type = "opinionated"
fills = ["schema-migration:orm"]
default = true
implements = "schema-migration:Model drift check"
roles = ["developer", "data-engineer", "reviewer"]
when_changed = ["**/*.cs", "**/Migrations/**"]
why = "Entity Framework Core is .NET's common data-access library, it follows the .NET support calendar, and it can tell when the model has changes no migration covers."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "entity-framework-core", registry = "nuget", package = "Microsoft.EntityFrameworkCore" }
version_policy = "latest_lts"
checked_version = "10.0.12"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
pin = "10.0.12"
source = "https://learn.microsoft.com/en-us/ef/core/what-is-new/"
evidence = "Entity Framework Core releases and support are aligned with .NET releases and support."
alternatives = ["Dapper", "linq2db"]
status = "active"
enforced_by = [
  { name = "tools", command = ["dotnet", "tool", "restore"] },
  { name = "drift", command = ["dotnet", "ef", "migrations", "has-pending-model-changes"] },
]
+++

# Entity Framework Core maps the .NET code to the database

It answers the orm choice of `aidd-team:schema-migration`.

## What the team does

- Reference EF Core and its provider at the version in `pin`, the release that matches the target framework.
- Configure each entity in its own `IEntityTypeConfiguration<T>` class, never with attributes scattered over the domain types.
- Turn on nullable reference types, so a required column is a non-nullable property.
- Read with `AsNoTracking()` unless the code updates what it reads. Log the SQL of a slow query, and check its plan.

## What the gate runs

Two `[[tests]]` entries, in order: `dotnet tool restore`, then `has-pending-model-changes`. A model change without its migration fails the change.
