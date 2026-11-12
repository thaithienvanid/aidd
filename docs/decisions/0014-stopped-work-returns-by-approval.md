# 14. Stopped work is taken up again by a new approval

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. `aidd approve` takes an Intent only today, and there is no `aidd cancel`.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

The project owner asked for one frame for everything that has a life, from open to closed to reopened. A cancelled Intent or Spec cannot be taken up again today, so it is stuck for good. What is the act that takes stopped work up again, and what is its name?

## Considered options

- **No way back.** It costs the stuck case, because a person who stopped work by mistake cannot resume it.
- **A command `aidd reopen`, a stored `reopening` object, two commit lines, and four actions.** It costs a new part for each piece. Reads of the design broke it in six places, among them a squash of two decisions, a reopened parent with closed children, and six rule files past their size limits.
- **A new approval.** It costs one ask. The approval takes the stop out of the file and covers today's content.

## Decision outcome

The chosen option is "a new approval", because a stop is a decision, and the act that undoes a decision is the same decision made the other way.

> A person takes stopped work up again by giving a new approval. `aidd approve <id>` on a cancelled Intent, Spec at `ready` or later, or proposal asks, takes the cancellation out, and writes a new approval. It takes back only the ids named on its command line, and has no command, object, line, or action of its own.

### The case that decided it

The first design added `aidd reopen`. Reads of the design broke it in six places, and a new approval removed all six at once. A stop is read from its commit, so editing `cancellation` out of the file lifts nothing. Only a newer approval lifts it, and it rests on today's content, never an earlier approval. It always asks a person, and a delegate defers.

### Consequences

- Good, because every closed state says how it is reopened, or says that it is final and what starts new work. A test fails on a closed status with neither.
- Good, because work closed by delivery, such as a merged Spec or a release, is never reopened in place. The way back is new work that names it.
- Bad, because a cancelled draft needs two asks to come back, the Intent's and then its own.

### Reopen when

A person needs to resume stopped work with no ask, for example in a run with nobody present.

## More information

[0013](0013-status-group-and-frame.md) defines open and closed. [0020](0020-an-approval-names-its-content.md) says how an approval holds.
