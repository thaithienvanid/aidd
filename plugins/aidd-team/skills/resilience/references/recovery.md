# Recovery decisions

Load this when you write the recovery line for a remote effect, or the fault-injection test that proves it.

## The decision table

| Would a person notice and care if it silently failed? | Run it twice: how many outcomes? | Recovery |
| --- | --- | --- |
| No | any | Drop it on failure; log the fact; write the decision at the call site (`# not retried: a missed view counter is acceptable`). |
| Yes | One (idempotent by nature: a read, a PUT of full state, an upsert on a natural key) | In-process retry with a timeout, backoff with jitter, and a budget inside the caller's deadline. |
| Yes | Two (an email, a charge, an append, a counter increment) | Durable record in the same transaction as the state change (outbox row or job), delivered by a sweep with a dedupe key the receiver honors. |
| Yes | Unsure | Treat it as two outcomes until a test shows one. |

Then, per dependency: **degrade** (serve a cached or partial answer, queue the action and say so) when the user can still do something useful; **fail hard** with a clear error when a wrong or stale answer is worse than none (money, permissions, safety).

## Retry policy in one place

```text
transient only:  timeout, connection reset, 429, 502, 503, 504
attempts:        3 at most (1 try + 2 retries)
backoff:         sleep = random(0, min(cap, base * 2^attempt))    # full jitter
budget:          sum of timeouts and sleeps < caller's deadline, with margin
layer:           here, and nowhere else on this path (SDK retries turned off)
honors:          Retry-After
```

## The outbox, in words

1. In one database transaction: change the business row, and insert an outbox row with a unique dedupe key (the order id plus the event name, for example).
2. A sweep reads unsent rows in order, delivers each with its dedupe key, and marks it sent after the receiver acknowledges.
3. If the acknowledgement is lost, the row is sent again; the receiver sees the same key and does nothing the second time.
4. The sweep's backlog age is a metric with an alert; rows that fail past a limit move to a dead-letter table with an owner.

## Fault-injection test: lost acknowledgement

The test drives the real code path against a receiver double that applies the effect and then fails to answer.

```text
given   a receiver that records each dedupe key it applies, and times out on the first call after applying it
when    the order is placed and the sweep runs until the outbox is empty
then    the receiver applied the effect exactly once
and     the outbox row is marked sent
and     the caller saw one retry, within its budget
```

Variants worth one test each: the process crashes between the business write and the send (the sweep still sends); the receiver returns 500 twice then succeeds (one effect); the receiver returns 400 (no retry, dead-letter).
