# 8. A request stores no status, and reads `pending`, `accepted`, `declined`, or `superseded`

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. Today a request has no status words, and these four are not in the code.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

A request is what someone wants, in their words. It moves from waiting, to taken up, to turned down or replaced. Should the request file hold a status, or should aidd read the status from other facts?

## Considered options

- **A stored status.** It costs a contradiction, because the word in the file can disagree with the items that take the request up.
- **A status read from facts.** It costs a lookup, because aidd must find the items that name the request, in one git call for each command.

## Decision outcome

The chosen option is "a status read from facts", because a fact stored once cannot contradict itself.

> A request stores no status. It reads `declined`, `superseded`, `accepted`, or `pending`, and the first that matches wins. What it stores are facts, namely its words, its `party`, its `source`, and, where it applies, a `decline`.

### The case that decided it

A Spec takes up a request and is rolled back later. A stored `accepted` would now be false, and no one would change it. Read from facts, the request returns to `pending`, and its line says "SPEC-1 took it up and was rolled back". An item takes a request up only while it names the request and is not stopped, so the reading follows the work.

### Consequences

- Good, because a request can never say `accepted` with nothing behind it.
- Good, because the word is the project owner's own. A request that Intake took up reads `accepted`, never `answered`.
- Bad, because `accepted` says only that Intake took the request up. For another party's request that can read as a promise, so each line pairs it with the item's own status, such as "accepted as INTENT-4 (draft)".

### Reopen when

A reader of `aidd status` still cannot tell a request that waits from a request that was taken up.

## More information

[METHOD.md](../METHOD.md) holds the method. [0009](0009-a-request-is-stored-when-taken-up.md) says when a request is stored, and [0027](0027-words-a-first-reader-gets-wrong.md) lists why `accepted` replaced `answered`.
