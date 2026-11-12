# 24. aidd's suggested answer to an open choice is a recommendation

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. `aidd standard` and the `standards/` folder keep their names until the knowledge work lands.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

A skill leaves some choices open, and aidd's library holds a suggested answer for each. Today that item is an "opinionated standard". The project owner asked what an item of aidd's library should be called, because "standard" already means a published source outside the project.

## Considered options

- **"Opinionated standard".** It costs a contradiction, because a standard is a published source and this is aidd's own.
- **"Answer".** It costs a clash: an answer is already a person's reply to an ask.
- **"Library rule".** It costs a false claim, because it binds nobody while it sits in the library.
- **"Recommendation".** It costs about 45 files by hand, and one cold read before it is built.

## Decision outcome

The chosen option is "recommendation", because it states what the item is and binds nobody.

> aidd's written answer to a choice that a skill leaves open is a recommendation. A project that adopts one gets a project rule in its config. A stack stays a stack, the ready bundle of recommendations for one technology, and "rule set" is dropped.

### The case that decided it

A recommendation cannot be broken, so it is knowledge, not a rule. Its shape differs from a project rule's. It has alternatives, a default, a maturity, and a checked tool, and no owner, level, or waiver. Two shapes need two words. "Standard" then means only a published source, and the registry holds one entry for each source.

### Consequences

- Good, because the config's two homes for a team's rules become one, with one item shape.
- Good, because a library stack applied once becomes the project's own stack, and the text says "the project's stack" or "a library stack".
- Bad, because `aidd standard` is replaced by `aidd rule add`, and the 244 library files each gain a `statement`.

### Reopen when

The cold read of the project rule's data model finds a reader who cannot answer task questions from it.

## More information

[0023](0023-knowledge-rules-capabilities.md) defines knowledge and rule. [docs/STANDARDS.md](../STANDARDS.md) describes the library today.
