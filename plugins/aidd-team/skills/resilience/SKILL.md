---
name: resilience
description: "Practice skill: recover each failure exactly once. Use in an aidd repository when a Task calls a service, queue, provider, or job, or someone says retries, timeouts, or duplicates."
metadata:
  checked: "2026-10-22"
---

# Resilience

**Use it when** a change crosses a process boundary (a remote call, a database write, a message, a job) whose failure somebody would notice. Use it too when a change adds or changes a retry, a timeout, a fallback, or a queue.

**Do not use when** the code is pure and in-process, with nothing to time out or retry. Load shedding and capacity planning for a whole system are the SRE's, through `aidd-team:performance` (references/scalability.md). This skill is the per-call decision.

## Standards

<!-- aidd:gen practice:resilience -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| Timeouts, retries, and backoff with jitter | — | 2026-10-16 (reviewed) | <https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/> |
| Addressing cascading failures: load shedding, retry budgets, and deadlines | — | 2026-10-16 (reviewed) | <https://sre.google/sre-book/addressing-cascading-failures/> |
| The transactional outbox: the state change and the message commit together, and a relay delivers the message | — | 2026-10-16 (reviewed) | <https://microservices.io/patterns/data/transactional-outbox.html> |

### Open choices

The team decides these. aidd's default holds until a `standards` entry fills one (`aidd standard list`).

| Choice | Question | aidd's default | Options |
| --- | --- | --- | --- |
| `durable-execution` | What runs a job whose steps must each finish once, over minutes or days? | An outbox and a sweep, or the durable-execution engine the host already runs, such as Cloudflare Workflows or AWS Step Functions. A dedicated engine where a run waits for a person or chains steps with side effects. | an outbox and a sweep, the host's own engine, Temporal, DBOS, Inngest, Restate |
<!-- aidd:end -->

## Specify

For every remote effect the change adds, write one line in the Spec's Design, decided with the table in [references/recovery.md](references/recovery.md):

- **Consequence:** would a person notice and care if this silently failed? If not, the decision is to drop it. Record that at the call site in a comment that says why, so the next reader does not "fix" it.
- **Repeat safety:** run the effect twice.
  - One outcome (a PUT of the same state, an upsert, a read): an in-process retry is enough.
  - Two outcomes (two emails, two charges, two rows) or unsure: write a durable record in the same transaction as the state change (an outbox row or a job). Have a sweep deliver it with a dedupe key the receiver honors (an idempotency key for an API, a unique constraint for a table).
- **Degrade or fail hard**, per dependency. State what the user sees while it is down (a cached value, a queued action, a clear error) in the Acceptance, so the verifier can check it.
- Add an Acceptance line for the lost acknowledgement: the effect happens, the reply is lost, the caller retries, and the effect still happens exactly once.

## Implement

- Every remote call has a timeout, set from the dependency's measured latency (a high percentile plus margin), never the library default of "forever".
- Retry only known transient errors (a timeout, a connection reset, 429, 502, 503, 504). Never retry on a broad exception. Never retry a 4xx that will fail the same way again.
- Retry at exactly one layer. A retry in the client, the SDK, and the queue multiplies. Three layers of three attempts make twenty-seven calls to an already struggling dependency.
- Use exponential backoff with full jitter, a small attempt cap, and a total retry budget that fits inside the caller's own timeout. Honor `Retry-After`.
- Retries stay under about a tenth of the requests to that dependency, so a struggling one gets less traffic, not more. Pass the remaining deadline downstream, and drop work whose caller has already given up.
- Break the circuit on a dependency that keeps failing: fail fast for a cool-down, then probe. Give each dependency its own bounded pool, so one slow dependency cannot hold every worker.
- The outbox row and the state change commit together. The sweep is idempotent, resumable, and alerts on its backlog age. Poison messages go to a dead-letter queue someone owns.

## Review

- Every new remote call has a timeout and a recorded recovery decision. No retry wraps a broad catch. Retries live at one layer. The effect with two outcomes has a durable record and a dedupe key. The degraded behavior matches the Acceptance.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Lost-acknowledgement test | the effect happens once after the reply is lost and the caller retries | a stub that commits then times out, or a proxy such as Toxiproxy; the sketch is in [references/recovery.md](references/recovery.md) |
| Timeout bound test | a timeout fires within its bound | a test against a slow stub |
| No retry on permanent errors | a non-transient error is not retried | a test that counts calls on a 4xx |
| Retry budget test | the retry budget ends before the caller's deadline | a test with a fixed clock |
| Breaker test | the breaker opens after its failure count, fails fast, and probes after the cool-down | a test with a failing stub and a fixed clock |

## Stop if

- A retry catches every exception, or retries sit at two layers.
- A remote call has no timeout, or the retry budget outlives the caller's deadline.
- An effect with two outcomes is retried in process with no dedupe key.
- Nobody can say what the user sees when a dependency is down.

## Hand off

- Done: the recovery line per effect, the timeouts, the retry policy, and the fault test. Next: the reviewer, and the SRE for the alerts on backlog age and breaker state. Needs: a dependency's latency or error data you could not measure. Stopped at: none, or the stop rule that fired.
