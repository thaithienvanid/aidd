---
name: performance
description: "Practice skill: make a change fast enough, against a budget. Use in an aidd repository when a Task has a latency, load, or size goal, or someone says it is slow or times out."
metadata:
  checked: "2026-10-22"
---

# Performance

**Use it when** a Task states a speed, capacity, or resource goal, or a regression in one is reported. Use it too when a change adds a query, a loop over remote calls, or a heavy page asset on a hot path. It owns query plans for new queries and indexes.

**Do not use when** nobody has measured a problem and no budget exists. Optimizing without a number is a refactor with extra risk. Capacity planning for a whole service is the SRE's. This skill is the change in front of you.

## Standards

<!-- aidd:gen practice:performance -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| The four golden signals, and the RED and USE methods | — | 2026-10-16 | <https://sre.google/sre-book/monitoring-distributed-systems/> |
| Core Web Vitals (LCP, INP, CLS) | 2024 thresholds | 2026-10-16 | <https://web.dev/articles/vitals> |
| Query plans reviewed for new queries and indexes | — | 2026-10-16 (reviewed) | — |
| Partitioning, clustering, and retention-tiering conventions, with cost per query and per pipeline run stated in the Spec and reviewed with the plan | — | 2026-10-16 (reviewed) | <https://www.finops.org/framework/domains/> |
| AWS Well-Architected Serverless Applications Lens | 2022-07-14 | 2026-10-16 | <https://docs.aws.amazon.com/wellarchitected/latest/serverless-applications-lens/welcome.html> |
| Use The Index, Luke: SQL indexing and tuning for developers | web edition | 2026-10-17 | <https://use-the-index-luke.com/> |
| PostgreSQL: using EXPLAIN to read query plans | PostgreSQL 18 | 2026-10-17 | <https://www.postgresql.org/docs/current/using-explain.html> |
| AWS Well-Architected Performance Efficiency Pillar | 2024-11-06 | 2026-10-17 | <https://docs.aws.amazon.com/wellarchitected/latest/performance-efficiency-pillar/welcome.html> |

### Open choices

The team decides these. aidd's default holds until a `standards` entry fills one (`aidd standard list`).

| Choice | Question | aidd's default | Options |
| --- | --- | --- | --- |
| `benchmark-tool` | Which tool runs the benchmarks and compares the head with its baseline? | The ecosystem's own benchmark harness, run on the base and the head on one machine, with a statistical comparison where the tool has one, such as benchstat or Criterion's change detection. | pytest-benchmark, Vitest bench, Go testing.B with benchstat, Criterion, JMH, BenchmarkDotNet, hyperfine |
<!-- aidd:end -->

## Specify

- Write the budget as an Acceptance line with a percentile, a load, and an environment. Examples: "p95 of `GET /orders` under 200 ms at 50 requests a second on the staging dataset", or "LCP at or under 2.5 s on the product page at p75". "Faster" is not a budget.
- Record the baseline on the base commit with the same command the regression guard will run. The Spec's `hypothesis` names the expected move.
- Put the guard in `tests.commands`, so the gate blocks a regression. A query that scans or stores a lot states its cost per query or per run.

## Implement

- Measure first. RED (rate, errors, duration) on the endpoint tells you whether it is slow. USE (utilization, saturation, errors) on CPU, memory, disk, network, connection pools, and locks tells you where it waits. Then profile the hot path with a sampling profiler or the browser's performance panel.
- Change one thing. Rerun the same command. Keep the change only if the numbers moved past run-to-run noise, otherwise revert it. Record each attempt and its result.
- Prefer removing work (fewer queries, less data, no repeated computation) over caching. A cache follows `aidd-team:caching`; scaling out, [references/scalability.md](references/scalability.md).

### Database and queries

- Read the plan for every new or changed query on production-shaped data (`EXPLAIN (ANALYZE, BUFFERS)` in PostgreSQL, `EXPLAIN ANALYZE` in MySQL). Look for sequential scans on large tables, row estimates far from actual rows, sorts spilling to disk, nested loops over many rows.
- Detect N+1: count queries per request in a test. Assert the count stays constant as the number of items grows. Fix with a join, a batched `IN` query, or the ORM's eager loading.
- An index serves a query that exists. Name the query. Match the column order to its filters and sort. Weigh the write cost. Adding or dropping an index is a migration: pair with `aidd-team:schema-migration`.
- Paginate by key (keyset) for large or changing lists. Set a statement timeout. The reading guide and the query-count test: [references/database.md](references/database.md).

### Serverless and edge

- Cold starts, memory sizing, connection limits, and edge consistency: [references/serverless.md](references/serverless.md).

## Review

- A budget, a baseline, and an after number from the same command and environment. Each kept change has its number. Every new query has a read plan and no N+1.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Regression guard | the budget holds on the head | the `apis-and-services:load-test` runner at a fixed arrival rate, its thresholds the budget; for a page, the Performance budget of `aidd-team:product-defaults`; or the `benchmark-tool` choice, base and head on one machine |
| Query-count test | no N+1 on a list endpoint | a test that counts queries as the item count grows |
| Plan check | a new query keeps the index it names | a test that reads the query's plan, such as `EXPLAIN (FORMAT JSON)`, and fails on a full scan of the table |

## Stop if

- There is no baseline, or the before and after numbers come from different commands or machines.
- The difference is inside run-to-run noise and you are about to keep the change anyway.
- An index or a cache is added without naming the query or the invalidation it serves.
- The guard is a report someone reads, not a command that fails.

## Hand off

- Done: the budget, the before and after numbers, the guard, and the plans read. Next: the reviewer, and the SRE to watch the SLI in the observe window. Needs: a production-shaped dataset or load environment the project lacks. Stopped at: none, or the stop rule that fired.
