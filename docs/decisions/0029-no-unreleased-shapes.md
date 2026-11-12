# 29. Nothing of an unreleased shape is read, handled, or tested

Accepted on 2026-11-14. In force for the list: `schemas/retired-names.json` holds no row. Decided for 1.0.0, not built yet. The code and tests that exist only for a pre-release shape are still there.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

aidd changed names and shapes while it was built. Readers and tests still handle some of the old ones. The first release is the first shape that any user holds. Should aidd keep reading what it never released?

## Considered options

- **Keep readers and tests for old shapes.** It costs code and tests for names that no user ever wrote, and they slow the suite. The suite holds more than 5,000 tests and runs past its budget.
- **Read nothing of an unreleased shape.** It costs an error, in place of a move, for a repository that still holds an old shape.

## Decision outcome

The chosen option is "read nothing of an unreleased shape", because a retired name exists to move a user's file, and no user holds one.

> The first release retires no name. Nothing of a shape that was never released is read, handled, or tested: no old key, no old status word, no old trailer.

### The case that decided it

The project owner asked to empty the list of retired names for the first release. The owner then asked to clean up the tests, because a test of a retired shape that nobody held proves nothing. The upgrade mechanism stays, because it serves the first release and every one after it. A test that pins that one pre-release thing is gone goes with the code that exists only for it. A real negative test of today's rules stays.

### Consequences

- Good, because the code and the suite shrink, and the retired list starts empty.
- Bad, because a repository of a pre-release shape fails with an error, so it must be rewritten by hand.

### Reopen when

A shape ships in a release and is later renamed. Then the retired list gets its first row.

## More information

[CONTRIBUTING.md](../../CONTRIBUTING.md) says how a release is cut.
