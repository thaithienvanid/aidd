# Scaling out

When one instance cannot meet the budget, add instances, not size. These rules make that work. The AWS Well-Architected Performance Efficiency Pillar is the frame.

## Stateless instances

- An instance keeps no state a later request needs. Sessions live in a store or a signed cookie, uploads go to object storage, and scheduled work runs under a lease (`aidd-team:data-access`). Then any instance can serve any request, and autoscaling can add or remove one at any time.
- Startup is fast and shutdown is graceful: an instance drains its in-flight requests and stops taking new ones before it exits.

## Scale on the right signal

- Scale on the signal that saturates first: CPU, concurrent requests, or queue depth. Set a minimum that covers the baseline load, and a maximum that the database, the downstream services, and the budget can bear.
- Size pools, workers, and connections with Little's law: requests in flight equal the arrival rate times the latency. At 200 requests a second and 50 ms, 10 are in flight on average. Load-test at the expected peak plus headroom.

## Absorb bursts

- Put a queue between a burst and the work (load leveling). The API accepts the request, enqueues it, and answers; workers drain the queue at the rate downstream can take.
- When downstream is full, slow down or shed at the edge (429 with `Retry-After`), never queue without a bound in memory (`aidd-team:resilience`).

## Data

- Read-heavy paths use a read replica or a cache (`aidd-team:caching`). A read that must see the caller's own write goes to the primary.
- Write-heavy data is partitioned by a key that spreads the load and keeps one unit's data together, such as the tenant or the account. Watch for a hot key. A query across partitions on a hot path is a design smell.
