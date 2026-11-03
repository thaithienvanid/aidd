---
type: llm
---

PASS if the reply does all of these:

- It asks for or sets a budget: a percentile latency at a stated load.
- It measures a baseline before changing anything.
- It points out the N+1 queries (one for the customer and one for the item count per order) and the missing pagination.
- It proposes fixing them with a join or eager loading and an aggregated count.
- It adds a regression guard, such as a query-count test that stays constant as orders grow, or a load test with a threshold.
- A cache, if mentioned, comes only after the numbers show it is still needed, with its key and invalidation named.

FAIL if the reply adds the cache as the fix without measuring, or does not notice the per-order queries. It also fails if it offers no test or threshold that would fail on a regression.
