# 14. Stopped work is taken up again by a new approval

Accepted on 2026-11-14. Revised on 2026-11-16: when a cancelled Spec may return, how a stop is read, and which ids `aidd approve` takes back. Decided for 1.0.0, not built yet. `aidd approve` takes Intents only today, and there is no `aidd cancel`. No code reads a `Cancels:` line, though `intent.cancel` and `spec.cancel` are in `schemas/risks.json`.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

The project owner asked for one frame for everything that has a life, from open to closed to reopened. A cancelled Intent or Spec cannot be taken up again today, so it is stuck for good. What is the act that takes stopped work up again, and what is its name?

## Considered options

- **No way back.** It costs the stuck case, because a person who stopped work by mistake cannot resume it.
- **A command `aidd reopen`, a stored `reopening` object, two commit lines, and four actions.** It costs a new part for each piece. Reads of the design broke it in six places, among them a squash of two decisions, a reopened parent with closed children, and six rule files past their size limits.
- **A new approval.** It costs one ask. The approval takes the stop out of the file and covers today's content.

## Decision outcome

The chosen option is "a new approval", because a stop is a decision, and the act that undoes a decision is the same decision made the other way.

> A person takes stopped work up again by giving a new approval. `aidd approve <id>` on a cancelled Intent, on a cancelled Spec at `ready` or later, or on a proposal asks, takes the cancellation out, and writes a new approval. It takes back only the ids named on its command line, and has no command, object, line, or action of its own. A decline is never lifted ([0011](0011-agents-accept-and-decline-at-report.md)).

### The case that decided it

The first design added `aidd reopen`. Reads of the design broke it in six places, and a new approval removed all six at once. A stop is read from its commit, never from the file alone, so editing `cancellation` out of the file lifts nothing: the item still reads cancelled, with an error. Only a newer approval that holds lifts it, and it rests on today's content, never an earlier approval. It always asks a person, and a delegate defers. A Spec stopped with its Intent comes back only when the person names it beside the Intent, as in `aidd approve INTENT-3 SPEC-7`. The ask gives that command, and nothing returns because a prompt listed it. The command refuses an item that new work replaced, a Spec whose Intent is `done`, and an item whose request was declined, each with its next step.

### Consequences

- Good, because every closed state says how it is reopened, or says that it is final and what starts new work. A test fails on a closed status with neither.
- Good, because work closed by delivery, such as a merged Spec or a release, is never reopened in place. The way back is new work that names it.
- Bad, because a cancelled draft needs two asks to come back, the Intent's and then its own once it is `ready`.
- Bad, because a stop that only an unmerged branch holds lasts as long as its commit. `git branch -D` and `git reset --hard` ask and name it. A rebase or an amend does not ask.

### Reopen when

A person needs to resume stopped work with no ask, for example in a run with nobody present.

## More information

[0013](0013-status-group-and-frame.md) defines open and closed. [0020](0020-an-approval-names-its-content.md) says how an approval holds.
