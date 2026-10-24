# Job stories and EARS

Load this when you slice backend or infrastructure work, write Acceptance lines that must be unambiguous, or state a business rule.

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

## Rules and decision tables

A business rule is a policy the product enforces, such as who gets free shipping. Find the rules before you write scenarios. Example mapping (Matt Wynne, Cucumber, 2015) does it in one short session. The story goes on one card, each rule on its own card below it, and the examples under each rule. A question nobody can answer goes on its own card and becomes an `open_questions` entry.

In Gherkin, a `Rule:` block groups the scenarios of one business rule, so a reader sees which rule each scenario proves.

A rule with three or more conditions hides its gaps in prose. Write it as a decision table instead, from OMG DMN 1.6:

- One column for each condition and one for the outcome. Each row is one combination, and it starts with its own Acceptance id.
- A hit policy says what happens when more than one row matches. **Unique** (U): the rows never overlap, so exactly one matches. **First** (F): the rows are read in order, and the first match wins. Prefer unique, because each row can then be read alone.
- Before Spec approval, name every gap (a combination no row matches) and every overlap (a combination two rows match under unique). Then a person decides each one, as a new row or an `open_questions` entry.

Example, with hit policy unique:

```text
Rule: shipping is free for members and for large orders at home (hit policy: unique)

| Id | Member | Order total | Destination | Shipping |
| --- | --- | --- | --- | --- |
| A1 | yes | any | domestic | free |
| A2 | no | 50 or more | domestic | free |
| A3 | no | under 50 | domestic | 4.99 |
| A4 | any | any | abroad | 14.99 |
```

Each row is one test, and its id goes in the test command's `covers`.
