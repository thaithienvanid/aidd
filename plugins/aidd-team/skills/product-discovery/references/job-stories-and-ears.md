# Job stories and EARS

Load this when you slice backend or infrastructure work, or write Acceptance lines that must be unambiguous.

## Job stories for work with no end user in sight

A user story ("As a user, I want...") has nothing to say when the actor is a scheduler, an operator, or another service. A job story names the situation instead:

> **When** <situation>, **I want to** <motivation>, **so that** <outcome>.

For backend and infrastructure work, every job story also answers three questions, because they are where such changes fail:

| Question | What to write |
| --- | --- |
| Idempotency | What a second run with the same input does. The answer should be "nothing changes"; if not, say what guards against it. |
| Failure and rollback | The real transaction boundaries: what commits together, what is left behind if it stops halfway, and how it is undone or resumed. |
| Concurrency | What happens when two runs, or a run and a user, touch the same data at once: a lock, a unique constraint, or a documented last-write-wins. |

Example:

```text
When the nightly invoice job runs for a billing period,
I want to create one invoice per active subscription,
so that customers are billed once and finance can close the period.

Idempotency:  a second run for the same period creates no invoice (unique key: subscription id + period).
Failure:      each invoice commits in its own transaction with its line items; a crash leaves whole
              invoices only, and a rerun creates the missing ones.
Concurrency:  a second job for the same period waits on an advisory lock and then finds nothing to do.
```

Each of those three lines becomes at least one Acceptance line and one test.

## EARS for Acceptance lines (optional)

EARS gives each requirement one of a few fixed shapes, so the trigger, the state, and the response are never left implicit.

| Pattern | Shape | Example |
| --- | --- | --- |
| Ubiquitous | The <system> shall <response>. | The export shall include every order the account owns. |
| Event-driven | When <trigger>, the <system> shall <response>. | When a payment webhook arrives twice with one event id, the service shall record one payment. |
| State-driven | While <state>, the <system> shall <response>. | While the provider is unavailable, the checkout shall queue the order and show its pending status. |
| Optional feature | Where <feature is present>, the <system> shall <response>. | Where single sign-on is enabled, the login page shall hide the password form. |
| Unwanted behavior | If <condition>, then the <system> shall <response>. | If the upload exceeds 10 MB, then the service shall reject it with a 413 problem document. |

Use EARS when Acceptance lines are being misread or argued over; Given/When/Then remains fine for the rest. Either way, each line names one observable result a test can check.
