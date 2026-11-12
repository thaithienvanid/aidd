# 22. The levels stay `ask`, `report`, and `allow`

Accepted on 2026-11-14. In force.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

Every action has one of three levels, `ask`, `report`, or `allow`. "An ask" is also a noun, for one occasion when the agent stops and puts a question. The project owner asked whether `request`, `report`, `allow` reads better. The owner also asked whether each thing an agent requests of a person should be named by its object, such as an approval request, a review request, an action request, or an information request.

## Considered options

- **A. Rename the levels to `request`, `report`, `allow`, with the family of requests.** It costs the word `ask` in 3,248 lines of 382 files, of which 1,450 hold the value itself. Four of six coding agents' own files still say `ask`, so every reader learns that aidd's `request` rule is written as the harness's ask rule.
- **B. Keep the level word, and name what is requested in the text.** It costs about 290 lines that say "an ask" or "the ask" as a noun. A bare level reads clearer as "ask" than as "request", because "request what?"
- **C. Keep the words as they are for now.** It costs nothing today and leaves B open.

## Decision outcome

The chosen option is "C, keep the words for now", because it costs nothing now, and only renaming the level is expensive later.

> The levels are `ask`, `report`, and `allow`, and "an ask" stays as a noun.

### The case that decided it

The project owner chose to keep the ask for now and may come back to it. The two ways back differ in cost. Naming what an agent requests in the text, option B, can be done at any time. Renaming the level, option A, breaks a stored value in every config that holds one, so it is cheap only before the first release tag.

### Consequences

- Good, because no stored value, harness rule, or reader's habit changes.
- Good, because two words stay apart. A request is what a person wants, and an ask is when the agent stops and puts a question to a person.
- Bad, because a bare "ask" does not say what is asked. Naming each ask by its object is left for later.

### Reopen when

The project owner revisits the words, and so before the first release tag if the level is to change.

## More information

[METHOD.md](../METHOD.md) holds the levels, and [0002](0002-advise-never-enforce.md) says who enforces them.
