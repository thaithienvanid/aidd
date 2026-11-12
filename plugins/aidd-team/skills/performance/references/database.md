# Database and query review

Load this when a change adds or alters a query, an index, or an ORM relation on a hot path.

## Reading a plan

Run it on production-shaped data; a plan on ten rows says nothing about ten million. `EXPLAIN ANALYZE` runs the statement, so wrap an `INSERT`, `UPDATE`, or `DELETE` in `BEGIN;` and `ROLLBACK;`, and never run it on production data.

| You see | It usually means | Try |
| --- | --- | --- |
| Sequential scan on a large table with a selective filter | No usable index for the filter | An index whose leading columns match the equality filters, then the range or sort column |
| Estimated rows far from actual rows (10x or more) | Stale or missing statistics, or correlated columns | `ANALYZE`, extended statistics, or a rewritten predicate |
| Sort with external merge / spill to disk | The sort does not fit in memory | An index that returns rows in order, or a smaller result set |
| Nested loop with a large outer side | The planner expected few rows | Fix the estimate first; a hash join may follow |
| Many buffers read for few rows returned | Scanning, then filtering | A covering or partial index, or a narrower query |
| Index scan, but slow | The index is not selective, or the query fetches many columns | Check selectivity; select only needed columns |

Record the plan before and after in the Task notes, with the row counts it ran on.

## N+1 detection

An N+1 is one query for a list, then one more query per item. It hides in tests with two items and appears in production with two thousand.

```text
given   the list endpoint with 1 item, then with 50 items
when    each request runs with a query counter (an ORM hook, a statement log, or a test database listener)
then    the query count is the same for both
```

Fix with a join, a single batched `WHERE id IN (...)`, or the ORM's eager loading for the relation. Then keep the test, because the next relation added to the serializer brings the N+1 back.

## Indexes

- Name the query each index serves; an index nobody's query uses is write cost and storage for nothing (`pg_stat_user_indexes` shows scans per index).
- Column order: equality filters first, then the range or the sort; a partial index for a hot subset (`WHERE status = 'open'`).
- Build without blocking writes (`CREATE INDEX CONCURRENTLY` in PostgreSQL, online DDL in MySQL), in its own migration step; see `aidd-team:schema-migration`.

## Guards that belong in the Spec

- The query-count test per list endpoint.
- A statement timeout on the connection role the application uses.
- A load test with thresholds on the endpoint whose budget the Acceptance names.
