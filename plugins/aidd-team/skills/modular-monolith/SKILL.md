---
name: modular-monolith
description: "Practice skill: one deployable, split into modules with enforced boundaries. Use in an aidd repository on a new project, or when a Task adds a module or changes its API, events, or data."
metadata:
  checked: "2026-10-09"
---

# Modular monolith

**Use it when** a new project starts (`aidd init`, `/aidd-team:mvp`), or a Task adds a module, changes a module's API, events, or data, or moves code across a boundary. It is on by default: `modular_monolith` in `[project.defaults]`.

**Do not use when** `[project.defaults] off` names `modular_monolith`. A client project or an existing structure keeps its structure, and an ADR records that decision.

## Standards

<!-- aidd:gen practice:modular-monolith -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| A modular monolith by domain: a public API per component, exclusive data ownership | — | 2026-10-09 | <https://shopify.engineering/deconstructing-monolith-designing-software-maximizes-developer-productivity> |
| CloudEvents: event attributes, a reverse-DNS type prefix, and lowercase extension names | 1.0.2 | 2026-10-09 | <https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md> |
| Application events between modules, after commit, with a publication registry | 2.1.1 | 2026-10-09 | <https://docs.spring.io/spring-modulith/reference/events.html> |
| The transactional outbox: the state change and the message commit together, and a relay delivers the message | — | 2026-09-30 (reviewed) | <https://microservices.io/patterns/data/transactional-outbox.html> |
| DORA software delivery performance metrics: change lead time, deployment frequency, failed deployment recovery time, change fail rate, and deployment rework rate | five-metric model | 2026-09-30 | <https://dora.dev/guides/dora-metrics-four-keys/> |

Steward: @thaithienvanid.

### Open choices

The team decides these. aidd's default holds until a `[[standards]]` entry fills one (`aidd standard list`).

| Choice | Question | aidd's default | Options |
| --- | --- | --- | --- |
| `module-boundaries` | Which check enforces the module dependency rules in CI? | The language's own visibility first, then an import-rule check over the whole repository on every change, with a violations baseline that never grows. | the language's own visibility (internal packages, package exports), an import-rule linter, an architecture test in the test suite |
<!-- aidd:end -->

## Plan

The seven principles:

1. Modules follow business capabilities, not technical layers.
2. Each module has one public door, its `api/`. All else is internal.
3. Each module owns its data. No module reads or writes the tables of another.
4. Dependencies point one way. Events break a cycle.
5. Machines enforce the rules: a boundary check fails the build.
6. Each module could become a service. Extract one only for a named reason.
7. The shared kernel stays small, generic, and stable, with no domain logic.

Start with 3 to 8 coarse modules, each a business noun. A good boundary: most changes touch one module, calls across it are few and coarse, each table has one owner, and one owner and one business sentence explain it. Write the module map in the architecture overview (`aidd new architecture`).

## Specify

- Layout: `apps/` (deployables, wiring only), `modules/<name>/` (`api/`, `internal/`, `migrations/`, a README from the aidd skill's `assets/module-readme.md`), `packages/` (no domain code), `docs/`.
- One module is one Task `scope`, one `[[owners.paths]]` entry, and one `[[tests]]` entry with `when_changed`.
- A change under `modules/*/api/` is a contract change (`baseline:module-api`, normal). A change to the violations baseline is major (`baseline:module-boundaries`).
- A new dependency between modules, a new event, a boundary move, or an extraction needs an ADR.

## Implement

- Call a module only through its `api/`, with DTOs and IDs, never ORM entities. Its errors are part of `api/`.
- Change one module per transaction, and never call another module inside it. Events carry the rest. A flow across modules is a saga.
- Events go through an outbox, at least once, to idempotent consumers: [references/events-and-data.md](references/events-and-data.md).
- One schema or table prefix per module. No foreign key or join across modules: [references/boundaries.md](references/boundaries.md).

## Review

- No import of another module's `internal/`, no query on its tables, no ORM entity in `api/`, no domain code in `packages/`.
- Anti-patterns: folders by layer, shared ORM entities, joins across modules, business logic in `shared/`, many tiny modules, cycles.

## Learn

Each quarter, check modules that change together, suppressed rules, and the shared kernel's size. Extract a module only for independent scaling, a different runtime, fault isolation, deploy contention, or compliance: [references/migrate-and-extract.md](references/migrate-and-extract.md).

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Boundary check | no import breaks the rules, and the violations baseline did not grow | the team's `module-boundaries` check over the whole repository |
| Cross-schema foreign keys | no foreign key crosses a module's schema | the query in references/boundaries.md returns zero rows |
| Event contract test | each event still matches every consumer's fixture | the provider builds the real event and validates it |
| Duplicate delivery test | one event delivered twice has one effect | deliver one event id twice; assert one change |

## Stop if

- A Task would touch another module's tables or import its `internal/`.
- The violations baseline would grow, or a suppression has no `[[project.waivers]]` entry with `until`.

## Hand off

- Done: the modules changed, their API and events, the boundary check green. Next: the reviewer. Needs: an ADR a person accepts. Stopped at: none, or the stop rule that fired.
