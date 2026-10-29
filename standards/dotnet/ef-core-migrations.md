---
id: dotnet/ef-core-migrations
type: opinionated
fills: [schema-migration:migration-tool]
default: true
implements: schema-migration:Migration up and down
roles: [developer, reviewer]
when_changed: ["**/Migrations/**", "**/*DbContext*.cs", ".config/dotnet-tools.json"]
why: "EF Core migrations are generated from the same model the code maps, each with an Up and a Down, so the schema history and the data access cannot drift apart."
reviewed: "2026-10-16"
maturity: established
tool:
  name: dotnet-ef
  registry: nuget
  package: dotnet-ef
version_policy: latest_lts
checked_version: "10.0.13"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "10.0.13"
source: https://learn.microsoft.com/en-us/ef/core/managing-schemas/migrations/
evidence: The migrations feature in EF Core provides a way to incrementally update the database schema to keep it in sync with the application's data model while preserving existing data in the database.
alternatives: [DbUp, FluentMigrator, Flyway]
status: active
enforced_by:
  - name: tools
    command: [dotnet, tool, restore]
  - name: script
    command: [dotnet, ef, migrations, script, --idempotent, --output, artifacts/migrations.sql]
  - name: up-down
    command: [dotnet, test, --configuration, Release, --filter-trait, Category=Migrations]
---

# EF Core migrations write and apply the .NET schema changes

It answers the migration-tool choice of `aidd-team:schema-migration`.

## What the team does

- Pin `dotnet-ef` at the version in `pin` in `.config/dotnet-tools.json`, the same release as EF Core.
- Add a migration with `dotnet ef migrations add`, and read the generated `Up` and `Down` before you commit. Never edit a migration that has run anywhere.
- Deploy with the idempotent script or a migrations bundle, never with `Database.Migrate()` at startup.
- Keep one test with the trait `Category=Migrations` on a Testcontainers database. Through `IMigrator`, it applies every migration, reverts to the one before the newest, and applies the newest again.

## What the gate runs

Three `tests` entries, in order: `dotnet tool restore`, the idempotent SQL script, and the migrations test. A migration that does not build into the script, or does not go up, down, and up again, fails the change.
