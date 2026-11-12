# 27. A word a first reader gets wrong is changed, or kept with its reason

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. Kept words such as `stack`, `built`, `ask`, and `from` are already in force; the new and renamed words are not in the code yet.
The project owner decided it. The architect and a reader who had never seen the design were consulted. Every contributor is informed through this record.

## Context and problem statement

The new design adds words for requests, the traceability matrix, and decisions. A reader who had never seen the design listed the words that they stopped at. Which are changed, and which stay?

## Considered options

- **Keep every word as designed.** It costs the first reader of the first release.
- **Change every word the reader stopped at.** It costs words that are right: a reader who stops at a word may need only its definition.
- **Change a word when a better one exists, and keep it with its reason when none does.** It costs a judgement for each word.

## Decision outcome

The chosen option is "change, or keep with its reason", because a rule of judgement fits each word's own case.

> A word that a first reader gets wrong is changed when a better word exists. Otherwise it stays, with its reason written down.

### The case that decided it

| Word | Result and reason |
| --- | --- |
| `answered`, a request's reading | `accepted`, the project owner's word, and the line pairs it with the item's own status |
| `shown` | `verified`. The reader proposed `proven`, but that word means "established" in the principle "Proven over new", and it claims more than a passing test shows |
| `continued` | `superseded`, because the first word read as "work kept going" |
| `party: person` | `party: owner`, because a client is a person too |
| `signed_off` beside `approved` | folds into `approved`: one word for one act |
| `answered_in` | `accepted_in`, and it holds paths, because a commit id does not survive a squash or a rebase |
| `claim:` and `unclaimed:` | `covers:` and `not covered:`, the word the Spec's own key uses |
| `shipped` and `merged` in the group `started` | stay: both are open, and the line says what remains |
| `stopped` beside `blocked` | stays: it is aidd's own word for an agent that stops and hands back |
| `served_by` | stays: it is the passive of `serves`, in the JSON only |
| `recommendation`, `stack`, `project rule`, `obligation`, `built`, `ask` | stay, each defined where it is first printed |

The same rule set the other words. They are a request's `party`, `source`, `files`, and `from`. They are the matrix's `acceptance` with `covers`, and `trace` with `served_by`, `proofs`, and `gaps`, and five gap codes. They also include the delegate's codes, and `error`, `warning`, and `note` in `aidd doctor`.

### Consequences

- Good, because each kept word has its reason on record, so the question is not asked again.
- Bad, because a few new names, such as `verified` and `party: owner`, were tested on no fresh reader as names. So the glossary defines `verified` and `met` as a pair.

### Reopen when

A new first reader stops at a word that this table keeps.

## More information

[0016](0016-verified-and-met.md), [0008](0008-a-request-stores-no-status.md), and [0026](0026-one-word-one-meaning.md) hold the cases behind three of these words.
