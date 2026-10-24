---
name: legacy-modernization
description: "Practice skill: replace a legacy system one slice at a time. Use in an aidd repository when a Task rewrites, ports, or migrates old code, data, or a cloud, or someone says strangler or cutover."
metadata:
  checked: "2026-10-22"
---

# Legacy modernization

**Use it when** a change replaces behavior that already runs in production. That's a rewrite, a port to another language or framework, or a move off a legacy system or vendor. It's also a data migration between stores, or a move from one cloud to another.

**Do not use when** the code is new, or the change reshapes a codebase into modules without replacing it. That's `aidd-team:modular-monolith` and its [migrate-and-extract reference](../modular-monolith/references/migrate-and-extract.md). A schema change inside one database is `aidd-team:schema-migration`.

## Standards

<!-- aidd:gen practice:legacy-modernization -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| Strangler fig and the patterns of legacy displacement: transitional architecture, event interception, legacy mimic, and parallel run | — | 2026-10-22 | <https://martinfowler.com/articles/patterns-legacy-displacement/> |
| Characterization tests: pin what legacy code does today, on real inputs, before changing it | — | 2026-10-22 (reviewed) | — |
| Expand and contract (parallel change) for data and APIs | — | 2026-10-16 (reviewed) | <https://martinfowler.com/bliki/ParallelChange.html> |
| Data migration reconciled by row counts and checksums per partition, with an idempotent, resumable copy and change data capture until cutover | — | 2026-10-22 (reviewed) | — |
| Cloud migration strategies, the 7 Rs: retire, retain, rehost, relocate, repurchase, replatform, and refactor | — | 2026-10-22 | <https://docs.aws.amazon.com/prescriptive-guidance/latest/large-migration-guide/migration-strategies.html> |
<!-- aidd:end -->

## Plan

- Name the outcome first: the cost, the risk, or the speed of change the replacement buys, and the legacy part retired at the end. A modernization that retires nothing leaves two systems to run.
- Never a big-bang rewrite. Slice by business capability or by a flow of events, one slice per Spec. Each slice ships, runs in production, and retires a piece of the legacy.
- List every consumer of the legacy, including the jobs, reports, and systems that read its database or files directly.
- Pick a strategy for each workload from the 7 Rs. Most moves rehost or replatform, so refactor only where the outcome needs it. A cloud-to-cloud move follows the same plan, with [references/cutover.md](references/cutover.md).

## Specify

- Characterization tests come first. They pin what the legacy does today, odd outputs included, on recorded real inputs. Redact personal data from those inputs first (`aidd-team:privacy-by-default`). They're green on the legacy before any new code exists.
- Route at the edge. A proxy, gateway, or router in front of both systems sends each request to the old or the new path, by route, tenant, or share. One switch moves a slice, and the same switch moves it back.
- A parallel run is the evidence. The new path takes the same inputs as the old one: shadow traffic for reads, and for writes a dry run that doesn't commit. The shadow path sends no email, payment, or other call outside the system. The diff of the two outputs is the Acceptance, and the Spec names each field the diff ignores, and why.
- Each slice names its rollback: the switch back, and what happens to the data the new path wrote meanwhile.

## Implement

- Never change behavior and modernize in the same commit. Make it equal first, then make it better.
- Transitional code, such as the router, an event interceptor, or an anti-corruption layer that translates the legacy model, has an owner and a removal Task.
- Data moves by copy, sync, and cutover, as [references/cutover.md](references/cutover.md) says. It's done when row counts and checksums match on both stores, never when the job exits 0.

## Verify

- The parallel-run diff is clean, or a person accepted each difference in the Spec. The characterization tests pass on both paths.

## Roll out

- Move traffic by share behind the router, as `aidd-team:release-rollout` says. The diff rate and the error rate are rollback triggers.
- After the observe window, retire the slice's legacy code, its routing rule, and its data copy. Keep a read-only export only where the law needs one.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Characterization tests | the legacy's current behavior is pinned before anything changes | approval tests (golden files) recorded from real inputs, green on the legacy first |
| Parallel run diff | the new path gives the old path's outputs on the same inputs | shadow or replayed traffic through both paths, a diff of normalized outputs, and a report of each difference |
| Migration reconciliation | the target holds every source row, unchanged | row counts per table and partition, and checksums over normalized rows, on both stores after the copy and after the cutover |
| Routing rollback test | one switch sends a slice back to the legacy | a test that flips the router and checks the next request reaches the old path |

## Stop if

- The plan cuts the whole system over at once, or a slice has no rollback.
- New code comes before the characterization tests are green on the legacy.
- A parallel-run difference is waved off without a person's decision, or a migration is called done on its exit code alone.
- Transitional code has no removal Task.

## Hand off

- Done: the slice plan, the characterization tests, the diff report, and the reconciliation result. Next: the reviewer, and the SRE for the cutover's observe window. Needs: a person's decision on each accepted difference. Stopped at: none, or the stop rule that fired.
