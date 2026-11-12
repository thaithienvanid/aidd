# 18. After three rounds of one review on one Spec, the work stops for a person

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. Only a Task's three retries for red tests exist today.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

A reviewer finds a problem, the developer fixes it, and a new review runs. Without a limit this repeats for ever. A Task already stops a person's attention after three retries of a red test. Do review rounds need a limit of their own?

## Considered options

- **No limit.** It costs the guard, because an agent and a reviewer can loop with no one watching. The graph has a rule that no cycle runs without a cap or a person in it.
- **Share the Task's three retries.** It costs clarity, because a red test and a review finding are different causes with different ways on.
- **Three rounds for each review type on one Spec, then a person.** It costs a person's time at round three.

## Decision outcome

The chosen option is "three rounds for each review type, then a person", because a loop with a cap needs a person at the cap.

> After three rounds of one review type on one Spec, the work stops for a person. A Task's three retries stay for red tests alone.

### The case that decided it

Every way back in the graph carries its bound. A red test on the newest commit returns to Implement three times at most. A finding left open by a review returns to Implement, and without its own bound it would be the one cycle with no cap. After the third round the person chooses: fix again, merge with the findings named, or re-plan with a revision of the Spec.

### Consequences

- Good, because no cycle in the graph is unbounded, and the stop names the person's three ways on.
- Bad, because a person is interrupted at round three, even for a finding that a fourth round would have closed.

### Reopen when

Teams report that three rounds stop work too often.

## More information

[METHOD.md](../METHOD.md) lists the ways back and their bounds.
