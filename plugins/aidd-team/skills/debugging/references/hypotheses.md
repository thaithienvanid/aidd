# Hypotheses and the debugging log

Load this when you have a red command and need to decide what to try first.

## Ranking hypotheses

Score each hypothesis on two things and try the cheapest likely one first.

| Hypothesis | If true, you will see | Experiment that could prove it false | Cost | Likelihood |
| --- | --- | --- | --- | --- |
| Stated as a cause, not a symptom | A specific observable value | One command, one changed variable | minutes | high / medium / low |

A hypothesis is falsifiable when some result of the experiment would make you drop it. "Something is wrong with caching" is not; "the second request reads a cached price older than the update" is.

Common first checks, in order of cost:

1. The plug: the running code is the code you are reading (branch, build, container tag, feature flag, configuration file, environment variable).
2. The data: the failing input is what you think it is (print it, do not assume it).
3. The boundary: the last point where the value was right and the first where it is wrong. Divide the path in half until they meet.
4. The change: what changed between the last good run and the first bad one (`git bisect run`, a dependency lockfile diff, the deploy log).
5. Time and order: clocks, time zones, retries, concurrency, test order, and shared state between tests.

## The log

Keep it in the Task or the Spec's notes while you work; it is the audit trail another person or agent picks up.

```text
Symptom:   POST /orders returns 500 "duplicate key" on the second order of the day for one customer
Red:       pytest tests/orders/test_create.py::test_second_order_same_day   (commit abc123, seed 7)
Minimal:   two orders, same customer, same UTC date; one order passes
H1 (cheap, likely): order number = customer id + date, no sequence
   predict: two orders on one date build the same number
   result:  confirmed, both are C42-2026-09-28
H2 (dropped): unique index missing -> index exists; the error is the index doing its job
Cause:     the order number is not unique per customer per day
Seam:      the order-number function and the repository insert; the test calls the service with a real test database
Fix:       add a per-customer daily sequence; red command green; suite green
Cleanup:   git grep DEBUG-ORD-17 -> empty
```

## After three failed fixes

Three fixes that each looked right and failed mean your picture of the system is wrong, not that a fourth guess is due. Stop and write down:

- what each fix assumed, and which assumption the failure disproved;
- whether the design makes the bug easy to write again (shared mutable state, two sources of truth, a hidden ordering dependency);
- the question a person or the architect must answer before anyone tries again.

Record `blockers` naming that question. aidd then shows the Task stopped and the Spec blocked, until a person re-plans it. The lesson goes to Learn.
