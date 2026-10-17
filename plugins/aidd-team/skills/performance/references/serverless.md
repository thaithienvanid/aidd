# Serverless and edge

A function or an edge worker starts, scales, and bills per request. So its performance has three costs a server does not: the cold start, the memory size that also sets the CPU, and each instance's connections.

- Measure cold starts apart: p95 with and without init (Lambda's `Init Duration`), under an arrival-rate load (k6 `constant-arrival-rate`), so new instances start. Cut them with a smaller bundle and lazy imports first. SnapStart, provisioned concurrency, or minimum instances cost money while idle, so the Spec says why.
- Size memory by a sweep (on Lambda it sets the CPU) and keep the cheapest that meets the budget. Set the timeout below the caller's. Open one pool per instance. Put a pooler (RDS Proxy, Hyperdrive) in front when instances times connections would pass the database's limit.
- At the edge, never read your own write from an eventually consistent store. The limits and prices: `aidd-team:cloud-and-infrastructure`, references/cost-and-performance.md.
