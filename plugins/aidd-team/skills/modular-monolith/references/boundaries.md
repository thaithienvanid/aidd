# Boundaries in code and in the database

Load this when a Task sets up the boundary check, adds a module, changes a module's data, or meets a boundary violation.

## The dependency rules

Write them once. The check runs on the whole repository for every change and fails the build:

- `apps/*` may import any module's `api/` and any package.
- `modules/X` may import `modules/Y/api` and `packages/*`, nothing else.
- Nothing outside `modules/X` imports `modules/X/internal`.
- `packages/*` never imports `modules/*` or `apps/*`.
- No cycle between modules. An event, or a merge of the two modules, breaks one.

A consumer imports an event's type from the publisher's `api/`, and gets the event from the event bus in `packages/`.

The tools are open choices: `modular-monolith:module-boundaries` (the check) and `ci-pipeline:workspace` (one package per module, one lockfile). `aidd standard list` shows the library standard for each ecosystem. Until the team adopts one, the default in words holds: the language's own visibility first, then an import-rule check.

## The violations baseline

An existing codebase starts with violations. Record them in `boundaries-baseline.<ext>` (the format the check reads), or in the tool's own config that its library standard names, such as `.importlinter`. The check then fails only on a new one.

- The baseline never grows. Count it each week: the count only goes down. Any change to the file is major (`baseline:module-boundaries`), for the `architecture` pool. Where the config has no such pool, `security` stands in.
- Each suppression gets a `project.waivers` entry with its reason, the person who approved it, and `until`. `aidd validate` warns 14 days before `until` and fails after it. The waiver names a project rule:

```yaml
project:
  rules:
    - id: module-boundaries
      level: must
      statement: "A module imports only another module's api/, and the violations baseline never grows."
      why: Boundaries decay within months without a machine check.
      check: boundaries
      owner: "@org/architecture"

  waivers:
    - rule: module-boundaries
      reason: billing reads orders.order_lines until the read model ships (ADR 0007)
      approved_by: "@lead"
      until: "2026-12-31"
```

## Data per module

| Database | Each module gets | The check |
| --- | --- | --- |
| Postgres | its own schema, and from about 10 engineers its own role that can touch only that schema | the foreign-key query below returns zero rows |
| SQLite or Cloudflare D1 (no schemas, no roles) | a table prefix (`orders_`), or its own database as the alternative | a lint check that each module's SQL and migrations name only tables with its prefix |

Name the schema, the roles, the tables, and the migrations as `references/systems.md` in `aidd-team:naming` says (section Database). Each module keeps its migrations in `modules/<name>/migrations/`. A foreign ID is a plain value, never a foreign key across modules.

The Postgres fitness function, for `tests`:

```sql
SELECT c.conname, t.relnamespace::regnamespace AS from_schema, r.relnamespace::regnamespace AS to_schema
FROM pg_constraint c
JOIN pg_class t ON t.oid = c.conrelid
JOIN pg_class r ON r.oid = c.confrelid
WHERE c.contype = 'f' AND t.relnamespace <> r.relnamespace;
```

With a role per module, each module gets its own small connection pool under its role, or sets `SET LOCAL ROLE` at the start of each transaction. A later split of the database is then a configuration change.

## Contract tests in process

A module test proves that a module works. A contract test proves that it still gives its consumers what they use. Write one for each published event, and for each `api/` call that two or more modules use.

- The consumer keeps a fixture of each event or response it depends on, next to its own tests.
- The provider's test builds the real event and validates it against each consumer's fixture (a JSON Schema or a typed snapshot).
- This runs on every change. After an extraction, move to consumer-driven contracts between services.

## Test layers

| Layer | Scope | Share |
| --- | --- | --- |
| Unit | the inside of one module, with fakes for its ports | most |
| Module integration | one module through its `api/`, with a real database in a container and fakes for other modules | many |
| Architecture | the dependency rules and the foreign-key query | a few, always on |
| End-to-end | the critical flows through `apps/` | few |
