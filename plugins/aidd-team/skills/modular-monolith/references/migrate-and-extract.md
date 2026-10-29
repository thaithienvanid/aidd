# Migrate a monolith, and extract a service

Load this when a team moves an existing codebase into modules, or when someone proposes to take a module out as a service. To replace a legacy system rather than reshape it, use `aidd-team:legacy-modernization`.

## Migrate an existing monolith

An existing structure keeps its structure until a person accepts an ADR that adopts this shape. Then migrate one module at a time while the product keeps shipping. Never stop for a rewrite.

1. Map what exists: the current import graph, and which code touches which tables. Many dependencies in one place show a missing boundary.
2. Agree on the target module map (the Plan section of the skill), and record it in an ADR.
3. Move the repository shape first: create `apps/`, `modules/`, and `packages/`, and move the entry point to `apps/`. Behavior does not change.
4. Turn on the boundary check in report-only mode, and record the current violations in the baseline file.
5. Pick the first module: few inbound dependencies and clear data (often notifications, catalog, or identity).
6. Carve it out: move its code to `modules/<name>/internal/`, add its `api/`, send its callers to the `api/`, and move its tables to its schema or prefix.
7. Remove its violations from the baseline, and enforce the rules for that module.
8. Repeat for the next module.

Plan by milestones with exit criteria, not by dates. The first module takes longest, because it sets the patterns.

| Milestone | Exit criteria |
| --- | --- |
| 1. Repository reshaped | `apps/`, `modules/`, and `packages/` exist; the app runs unchanged; the check runs in report-only mode with a baseline |
| 2. First module carved | one module has its `api/`, its own schema or prefix, and no baseline line; its rules are enforced |
| 3. Half enforced | half of the modules are carved and enforced; the module template exists |
| 4. All boundaries enforced | the baseline file is empty; every rule fails the build |
| 5. Data enforced | each module has its own database role (where the database has roles); the foreign-key query returns zero rows |

Each milestone is an Epic (`aidd new epic`), and each carved module is a Spec. A change to the baseline is major, so a person from the architecture pool sees each one.

## Valid reasons to extract a service

| Reason | Signal |
| --- | --- |
| Independent scaling | one module needs much more CPU, memory, or instances than the rest |
| Different runtime | the module needs another language, a GPU, or long-running jobs |
| Fault isolation | a failure in the module takes down features that do not depend on it |
| Deploy contention | teams wait for each other's releases again and again |
| Compliance | the data must be kept apart physically (PCI DSS scope, regional residency) |

Measure first. Per-module database load is the best early signal. Fashion, a new team, or "microservices are modern" is not a reason.

## Extraction steps

1. Confirm that the module follows the rules: only its `api/` is imported, it has its own schema, and nothing joins its tables.
2. Write an ADR that names the reason and the success measure.
3. Add `apps/<name>-service`, which hosts the existing module code behind HTTP or gRPC.
4. In the other modules, replace the in-process `api/` client with a remote client that has the same interface.
5. Move the events to a broker: the outbox relay now publishes there, and the consumers do not change.
6. Move the module's schema to its own database.
7. Run both paths behind a flag, compare the results, then switch over and delete the in-process wiring. The comparison is a parallel run, and `aidd-team:legacy-modernization` says how to diff it.

The code stays in the same repository, so shared tooling, types, and atomic refactors keep working after the extraction. Move the contract tests to consumer-driven contracts between services.
