---
type: llm
---

PASS if the reply says that a timed-out charge may already have succeeded, so retrying it can charge twice, and fixes that with an idempotency key the provider honors (or a durable record delivered with a dedupe key); adds a timeout to the call; retries only transient errors instead of every exception; keeps retries at one layer (the function or the queue, not both); uses backoff with jitter within a budget; does not hide failure behind a returned "unknown" status; and proposes a test where the charge succeeds but the reply is lost and the retry still produces exactly one charge.
FAIL if the reply only tunes the number of retries or the sleep, keeps `except Exception` as the retry condition, keeps retries in both the function and the queue, omits the double-charge risk, or proposes no test for the lost acknowledgement.
