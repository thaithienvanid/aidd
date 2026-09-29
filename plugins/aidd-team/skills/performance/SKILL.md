---
name: performance
description: "Practice skill: make a change fast enough, measured against a budget, and keep it that way. Use when a Task has a latency, throughput, memory, cost, or page-speed goal, or when someone says it is slow, it times out, the page takes forever, the query is slow, the database is at 100% CPU, p95 or p99 went up, too many queries, N+1, a missing index, a full table scan, EXPLAIN, a load test, a benchmark, Core Web Vitals, LCP, INP, or bundle size: a budget as an Acceptance line, a baseline first, profile, change one thing, keep or revert on the numbers, a regression guard in the Spec's test commands, and query and index review."
metadata:
  checked: "2026-09-28"
---

# Performance

**Use it when** a Task states a speed, capacity, or resource goal, when a regression in one is reported, or when a change adds a query, a loop over remote calls, or a heavy page asset on a hot path.

**Do not use when** nobody has measured a problem and no budget exists; optimizing without a number is a refactor with extra risk. Capacity planning for a whole service is the SRE's; this skill is the change in front of you.

## Standards

- Brendan Gregg's USE method for resources: utilization, saturation, and errors for every resource.
- The RED method for services (Tom Wilkie): rate, errors, and duration per endpoint.
- Core Web Vitals (web.dev): LCP, INP, and CLS at the 75th percentile of field data for web pages.

## Specify, before Spec approval

- Write the budget as an Acceptance line with a percentile, a load, and an environment: "p95 of `GET /orders` under 200 ms at 50 requests a second on the staging dataset", or "LCP at or under 2.5 s on the product page at p75". "Faster" is not a budget.
- Record the baseline on the base commit with the same command the regression guard will run; the Spec's `hypothesis` names the expected move.
- Put the guard in `[[tests.commands]]`: a k6 run with `thresholds`, a Lighthouse CI budget, or a benchmark that fails past a threshold, so the gate blocks a regression.

## Implement

- Measure first: RED on the endpoint tells you whether it is slow; USE on CPU, memory, disk, network, connection pools, and locks tells you where it waits. Then profile the hot path (a sampling profiler, a flame graph, the browser's performance panel).
- Change one thing, rerun the same command, and keep the change only if the numbers moved past run-to-run noise; otherwise revert it. Record each attempt and its result.
- Prefer removing work (fewer queries, less data, no repeated computation) over caching; a cache names its key, its expiry, and how it is invalidated.

## Database and queries

- Read the plan for every new or changed query on production-shaped data (`EXPLAIN (ANALYZE, BUFFERS)` in PostgreSQL, `EXPLAIN ANALYZE` in MySQL): look for sequential scans on large tables, row estimates far from actual rows, sorts spilling to disk, and nested loops over many rows.
- Detect N+1: count queries per request in a test and assert the count stays constant as the number of items grows. Fix with a join, a batched `IN` query, or the ORM's eager loading.
- An index serves a query that exists: name the query, match the column order to its filters and sort, and weigh the write cost. Adding or dropping an index is a migration: pair with `aidd-team:schema-migration` (concurrent builds, no long locks).
- Paginate by key (keyset) for large or changing lists; select only the columns you use; set a statement timeout.

The reading guide and the query-count test are in [references/database.md](references/database.md).

## Test commands

- The regression guard: `k6 run` with thresholds (`http_req_duration: ['p(95)<200']`), `lhci autorun` with a budget file, or a benchmark (pytest-benchmark, JMH, Go `testing.B`, Criterion) compared against the stored baseline with a threshold.
- A query-count test for every list endpoint; a plan check for a new query where the project keeps one.

## Review

- A budget, a baseline, and an after number from the same command and environment; each kept change has its number; the guard is in the test commands; every new query has a read plan and no N+1.

## Hand off

- Done: the budget, the before and after numbers, the guard, and the plans read. Next: the reviewer, and the SRE to watch the SLI in the observe window. Needs: a production-shaped dataset or load environment the project lacks. Stopped at: none, or the stop rule that fired.

## Stop if

- There is no baseline, or the before and after numbers come from different commands or machines.
- The difference is inside run-to-run noise and you are about to keep the change anyway.
- An index or a cache is added without naming the query or the invalidation it serves.
- The guard is a report someone reads, not a command that fails.
