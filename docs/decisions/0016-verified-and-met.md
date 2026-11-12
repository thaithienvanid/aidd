# 16. A requirement reads `verified` by proof and `met` by a person's review

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. `met` is already in `schemas/product-scope.schema.json` and `schemas/product-status.schema.json`; `verified` and the traceability matrix are not in the code yet.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

A requirement has no metric. Something must say when it is reached. When does a requirement read as shown, and does that need a person to have read the claim?

## Considered options

- **Only when a person reviewed it.** It costs one person's review for each requirement, even where the tests already prove it.
- **When proof stands, under whatever approved the Spec by the project's own rules, and the line says which.** It costs a gap, because a requirement can read `verified` though no person read the claim.
- **Never by proof.** It costs the matrix, because every requirement would wait on a person.

## Decision outcome

The chosen option is "proof stands, and the line says which approval", because the project's own rules already say how much a person must read, and a status must not claim more.

> A requirement reads `verified` when proof stands. An acceptance item covers it, a test command covers that item, and the Spec is done and released. The line says whether a person, a delegate, or the rule's level approved the Spec. `met` always means a person's own review.

### The case that decided it

A status that said a person had decided when none had would be false. So there are two words with two causes. `verified` follows production and is read from proof, and nobody writes it. `met` is a person's result, and it wins, so after any result only a person's result moves the requirement again. The line `verified by SPEC-2 A1 (done 2026-11-20, approved by the rule: report)` shows which approval stands behind the word.

### Consequences

- Good, because the matrix prints each requirement's proof and each gap, and an auditor sees the approval behind it.
- Bad, because a tracker's user may expect the reverse, `verified` for a person's check. The glossary and `aidd status product --help` define the two words as a pair.
- Bad, because the link from an acceptance item to a requirement is a claim about meaning. Nothing checks it, so the reviewer reads each one.

### Reopen when

Teams read `verified` as a person's check despite the pair definition.

## More information

[0027](0027-words-a-first-reader-gets-wrong.md) says why the word is not `shown` or `proven`.
