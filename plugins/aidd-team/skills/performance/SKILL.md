---
name: performance
description: "Practice skill: make a change fast enough, against a budget. Use in an aidd repository when a Task has a latency, load, or size goal, or someone says it is slow or times out."
metadata:
  checked: "2026-09-30"
---

# Performance

**Use it when** a Task states a speed, capacity, or resource goal, or a regression in one is reported. Use it too when a change adds a query, a loop over remote calls, or a heavy page asset on a hot path. It owns query plans for new queries and indexes.

**Do not use when** nobody has measured a problem and no budget exists. Optimizing without a number is a refactor with extra risk. Capacity planning for a whole service is the SRE's. This skill is the change in front of you.

## Standards

<!-- aidd:gen practice:performance -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| The four golden signals, and the RED and USE methods | — | 2026-09-28 | <https://sre.google/sre-book/monitoring-distributed-systems/> |
| Core Web Vitals (LCP, INP, CLS) | 2024 thresholds | 2026-09-28 | <https://web.dev/articles/vitals> |
| Query plans reviewed for new queries and indexes | — | 2026-09-25 (reviewed) | — |
| Partitioning, clustering, and retention-tiering conventions, with cost per query and per pipeline run stated in the Spec and reviewed with the plan | — | 2026-09-29 (reviewed) | <https://www.finops.org/framework/domains/> |
| AWS Well-Architected Serverless Applications Lens | 2022-07-14 | 2026-09-30 | <https://docs.aws.amazon.com/wellarchitected/latest/serverless-applications-lens/welcome.html> |

Steward: @thaithienvanid.
<!-- aidd:end -->

## Specify

- Write the budget as an Acceptance line with a percentile, a load, and an environment. Examples: "p95 of `GET /orders` under 200 ms at 50 requests a second on the staging dataset", or "LCP at or under 2.5 s on the product page at p75". "Faster" is not a budget.
- Record the baseline on the base commit with the same command the regression guard will run. The Spec's `hypothesis` names the expected move.
- Put the guard in `[[tests.commands]]`, so the gate blocks a regression. A query that scans or stores a lot states its cost per query or per run.

## Implement

- Measure first. RED (rate, errors, duration) on the endpoint tells you whether it is slow. USE (utilization, saturation, errors) on CPU, memory, disk, network, connection pools, and locks tells you where it waits. Then profile the hot path (a sampling profiler, a flame graph, the browser's performance panel).
- Change one thing. Rerun the same command. Keep the change only if the numbers moved past run-to-run noise, otherwise revert it. Record each attempt and its result.
- Prefer removing work (fewer queries, less data, no repeated computation) over caching. A cache names its key, its expiry, and how it is invalidated.

### Database and queries

- Read the plan for every new or changed query on production-shaped data (`EXPLAIN (ANALYZE, BUFFERS)` in PostgreSQL, `EXPLAIN ANALYZE` in MySQL). Look for sequential scans on large tables, row estimates far from actual rows, sorts spilling to disk, nested loops over many rows.
- Detect N+1: count queries per request in a test. Assert the count stays constant as the number of items grows. Fix with a join, a batched `IN` query, or the ORM's eager loading.
- An index serves a query that exists. Name the query. Match the column order to its filters and sort. Weigh the write cost. Adding or dropping an index is a migration: pair with `aidd-team:schema-migration`.
- Paginate by key (keyset) for large or changing lists. Select only the columns you use. Set a statement timeout. The reading guide and the query-count test: [references/database.md](references/database.md).

### Serverless and edge

- Measure cold starts apart: p95 with and without init (Lambda's `Init Duration`), under an arrival-rate load (k6 `constant-arrival-rate`), so new instances start. Cut them with a smaller bundle and lazy imports first. SnapStart, provisioned concurrency, or minimum instances cost money while idle, so the Spec says why.
- Size memory by a sweep (on Lambda it sets the CPU) and keep the cheapest that meets the budget. Set the timeout below the caller's. Open one pool per instance. Put a pooler (RDS Proxy, Hyperdrive) in front when instances times connections would pass the database's limit.
- At the edge, never read your own write from an eventually consistent store. The limits and prices: `aidd-team:cloud-and-infrastructure`, references/cost-and-performance.md.

## Review

- A budget, a baseline, and an after number from the same command and environment. Each kept change has its number. The guard is in the test commands. Every new query has a read plan and no N+1.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Regression guard | the budget holds on the head | `k6 run` (k6 v2.3.0) with thresholds (`http_req_duration: ['p(95)<200']`), `npx @lhci/cli@0.15.1 autorun` with a budget file, or a benchmark (pytest-benchmark, JMH, Go `testing.B`, Criterion) against the stored baseline |
| Query-count test | no N+1 on a list endpoint | a test that counts queries as the item count grows |
| Plan check | a new query keeps its expected plan | a stored-plan comparison, where the project keeps one |

## Stop if

- There is no baseline, or the before and after numbers come from different commands or machines.
- The difference is inside run-to-run noise and you are about to keep the change anyway.
- An index or a cache is added without naming the query or the invalidation it serves.
- The guard is a report someone reads, not a command that fails.

## Hand off

- Done: the budget, the before and after numbers, the guard, and the plans read. Next: the reviewer, and the SRE to watch the SLI in the observe window. Needs: a production-shaped dataset or load environment the project lacks. Stopped at: none, or the stop rule that fired.
