# 13. A status, its group, and open or closed are three layers

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. `x-groups` in `schemas/common.schema.json` holds the older groups today, with `rolled_back` under `completed`; the new grouping, Intent's `in_progress`, and the frame are not built yet.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

The project owner asked why a work item read "backlog" when "open" was expected. The word was a status group shown where a status belongs. Separately, `done`, `completed`, and `closed` all seemed to say one thing. How many layers of state are there, and what is each word for?

## Considered options

- **Make `open`, `closed`, and `reopened` statuses.** It costs a clash, because `open` is also what several types call a waiting state.
- **Rename `done` to `completed`.** It costs 472 lines in 67 files, and it makes the group and the status one word for two things.
- **Three layers.** It costs one rule: no status is a frame word, and a printed line never shows a group where a status belongs.

## Decision outcome

The chosen option is "three layers", because each word then has one level and one meaning.

> A status is a thing's own word for where it stands. Its status group is one of `backlog`, `unstarted`, `started`, `completed`, or `cancelled`, the same five for every type. The frame is open for the first three groups and closed for the last two. `done` stays a status, `completed` is a group, and closed is the frame's word.

### The case that decided it

A board that lists work by group showed a rolled-back Spec under "Completed", and a client reads that as delivered. The test for a group is whether what the thing was for still stands. Nothing of a rolled-back Spec is live, so `rolled_back` and `retired` belong to `cancelled`. An Intent gains a sixth read status, `in_progress`, when a Spec under it is in progress or further, so it sits in `started` instead of `unstarted`. `merged` and `shipped` stay in `started`, because a merged Spec still waits for its release and a shipped Intent for its measurement.

### Consequences

- Good, because a board, a tracker mirror, and `aidd status` share one group vocabulary.
- Good, because each closed status can say how it is reopened ([0014](0014-stopped-work-returns-by-approval.md)).
- Bad, because the group `started` holds states that are waiting. Each line says what remains.

### Reopen when

A tracker that mirrors aidd needs a sixth group.

## More information

[0026](0026-one-word-one-meaning.md) holds the rule that one word has one meaning in every type.
