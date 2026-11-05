---
type: llm
---

PASS if the reply does all of these:

- It says a timed-out charge may already have succeeded, so retrying it can charge twice.
- It fixes that with an idempotency key the provider honors, or a durable record delivered with a dedupe key.
- It adds a timeout to the call, and retries only transient errors instead of every exception.
- It keeps retries at one layer: the function or the queue, not both.
- It uses backoff with jitter within a budget.
- It does not hide failure behind a returned "unknown" status.
- It proposes a test where the charge succeeds but the reply is lost, and the retry still produces exactly one charge.

FAIL if the reply only tunes the number of retries or the sleep, or keeps `except Exception` as the retry condition. It also fails if it keeps retries in both the function and the queue, omits the double-charge risk, or proposes no test for the lost acknowledgement.
