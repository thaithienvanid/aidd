---
name: resilience
description: "Practice skill: decide how each failure is recovered, and prove that recovery happens exactly once. Use when a Task calls another service, a database, a queue, a payment or email provider, a webhook, or a scheduled job, or when someone mentions retries, timeouts, backoff, idempotency, duplicates, double charges, lost messages, at-least-once delivery, an outbox, a dead-letter queue, a circuit breaker, fallbacks, degraded mode, or what happens if this call fails: recovery by consequence and repeat safety, retry hygiene, timeouts, circuit breaking and load shedding, degrade or fail per dependency, and a lost-acknowledgement fault test."
metadata:
  checked: "2026-09-28"
---

# Resilience

**Use it when** a change crosses a process boundary (a remote call, a database write, a message, a job) whose failure somebody would notice, or when it adds or changes a retry, a timeout, a fallback, or a queue.

**Do not use when** the code is pure and in-process; there is nothing to time out or retry. Load shedding and capacity planning for a whole system are the SRE's, through `aidd-team:observability`; this skill is the per-call decision.

## Standards

- AWS Builders' Library, "Timeouts, retries, and backoff with jitter" (Marc Brooker).
- Google SRE book, chapter 22, "Addressing Cascading Failures".
- The transactional outbox pattern (Chris Richardson, microservices.io).

## Specify, before Spec approval

For every remote effect the change adds, write one line in the Spec's Design, decided with the table in [references/recovery.md](references/recovery.md):

- **Consequence:** would a person notice and care if this silently failed? If not, the decision is to drop it; record that at the call site in a comment that says why, so the next reader does not "fix" it.
- **Repeat safety:** run the effect twice. One outcome (a PUT of the same state, an upsert, a read): an in-process retry is enough. Two outcomes (two emails, two charges, two rows) or unsure: write a durable record in the same transaction as the state change (an outbox row or a job), and have a sweep deliver it with a dedupe key the receiver honors (an idempotency key for an API, a unique constraint for a table).
- **Degrade or fail hard**, per dependency: what the user sees while it is down (a cached value, a queued action, a clear error), stated in the Acceptance so the tester can check it.
- An Acceptance line for the lost acknowledgement: the effect happens, the reply is lost, the caller retries, and the effect still happens exactly once.

## Implement

- Every remote call has a timeout, set from the dependency's measured latency (a high percentile plus margin), never the library default of "forever".
- Retry only errors that are known transient (a timeout, a connection reset, 429, 503); never retry on a broad exception, and never retry a 4xx that will fail the same way again.
- Retry at exactly one layer. A retry in the client, the SDK, and the queue multiplies: three layers of three attempts is twenty-seven calls to a dependency that is already struggling.
- Exponential backoff with full jitter, a small attempt cap, and a total retry budget that fits inside the caller's own timeout; honor `Retry-After`.
- Break the circuit on a dependency that keeps failing: fail fast for a cool-down, then probe; shed load at the entry point (bounded queues, rejecting early with 503) rather than letting every request wait.
- The outbox row and the state change commit together; the sweep is idempotent, resumable, and alerts on its backlog age; poison messages go to a dead-letter queue someone owns.

## Test commands

- A fault-injection test that drops the acknowledgement after the effect (a stub that commits then times out, or a proxy such as Toxiproxy) and asserts one effect after the retry; see the sketch in [references/recovery.md](references/recovery.md).
- A test that a timeout fires within its bound; a test that a non-transient error is not retried; a test that the retry budget ends before the caller's deadline; a chaos experiment in staging for the circuit breaker, when the platform has one.

## Review

- Every new remote call has a timeout and a recorded recovery decision; no retry wraps a broad catch; retries live at one layer; the effect with two outcomes has a durable record and a dedupe key; the degraded behavior matches the Acceptance.

## Hand off

- Done: the recovery line per effect, the timeouts, the retry policy, and the fault test. Next: the reviewer, and the SRE for the alerts on backlog age and breaker state. Needs: a dependency's latency or error data you could not measure. Stopped at: none, or the stop rule that fired.

## Stop if

- A retry catches every exception, or retries sit at two layers.
- A remote call has no timeout, or the retry budget outlives the caller's deadline.
- An effect with two outcomes is retried in process with no dedupe key.
- Nobody can say what the user sees when a dependency is down.
