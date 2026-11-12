# 17. An Intent serves a list of items, with at most one measured goal

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. `serves` on an Intent is a single value in `schemas/intent.schema.json` today.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

An Intent takes some items of the product scope on and says how a person will know it worked. Today it serves exactly one item. How does it name the requirements it takes on besides its goal?

## Considered options

- **Keep one item.** It costs one Intent for each requirement, because an Intent could not take several on.
- **Two keys, `serves` and a second for requirements.** It costs two words for one link.
- **One word, `serves`, as a list, with at most one measured goal.** It costs a change to 125 files. The sentence "an Intent serves exactly one item" becomes "one measured goal, and any requirements".

## Decision outcome

The chosen option is "`serves` as a list, with at most one measured goal", because one word then names one link at every scope.

> `serves` on an Intent is a list. At most one item in it has a metric, and `success_criteria` is required only when the Intent serves an item with a metric.

### The case that decided it

INTENT-1 serves an outcome, `Outcome-1`, and two requirements. It measures the outcome with one success criterion. An Intent that serves requirements alone needs no criteria, so it reads `done` the day it ships. The limit keeps each success criterion tied to one measured goal, and the requirements ride along.

### Consequences

- Good, because a single Intent can ship a goal and the requirements around it.
- Good, because the link has one word and one test: finishing the work does not finish the item, because a result or a proof does.
- Bad, because the rename touches 125 files and a schema rule that asks for success criteria whenever `serves` is set must loosen.

### Reopen when

Teams need to measure two goals in one Intent.

## More information

[0016](0016-verified-and-met.md) says when a served requirement reads as reached.
