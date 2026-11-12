# 13. A status, its group, and open or closed are three layers

Accepted on 2026-11-14. Revised on 2026-11-16 to add a sixth Intent status, `in_progress`. Decided for 1.0.0, partly built. The five groups (`status_group` in `schemas/common.schema.json`), the frame (`closes_in_groups` in `schemas/lifecycles.json`), and the vocabulary test (V1 to V3 in `tests/data_rules.py`) are in force. A rolled-back Spec still sits in `completed`, and an Intent reads `active`. The Intent statuses `merged`, `shipped`, and `in_progress` do not exist yet, and neither does the Spec status `built`.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

The project owner asked why a work item read "backlog" when "open" was expected. The word was a status group shown where a status belongs. Separately, `done`, `completed`, and `closed` all seemed to say one thing. How many layers of state are there, and what is each word for? Does an Intent show as started once one of its Specs is?

## Considered options

- **Make `open`, `closed`, and `reopened` statuses.** It costs a clash, because `open` is also what several types call a waiting state.
- **Rename `done` to `completed`.** It costs 472 lines in 67 files, and it makes the group and the status one word for two things.
- **Three layers.** It costs one rule: no status is a frame word, and a printed line never shows a group where a status belongs.
- **Five Intent statuses, with no `in_progress`.** It costs a board by group, which shows an Intent under "Unstarted" while its Specs are built.

## Decision outcome

The chosen option is "three layers, and six Intent statuses", because each word then has one level and one meaning.

> A status is a thing's own word for where it stands. Its status group is one of `backlog`, `unstarted`, `started`, `completed`, or `cancelled`, the same five for every type. The frame is open for the first three groups and closed for the last two. `done` stays a status, `completed` is a group, and closed is the frame's word. An Intent also reads `in_progress`: its approval holds, it has not shipped, and a Spec of it reads `in_progress`, `built`, `merged`, or `done`. It is read from its Specs and never stored. The limit on Intents in flight (`max_in_flight` in the intent order) counts an Intent that reads `approved` or `in_progress`. `review_every_days` warns on one that still reads either, so `in_progress` is not exempt.

### The case that decided it

A board that lists work by group showed a rolled-back Spec under "Completed", and a client reads that as delivered. The test for a group is whether what the thing was for still stands. Nothing of a rolled-back Spec is live, so `rolled_back` and `retired` belong to `cancelled`. `merged` and `shipped` stay in `started`, because a merged Spec still waits for its release and a shipped Intent for its measurement. The project owner chose the sixth Intent status so that a board shows an Intent under "Started" while its Specs are built. It leaves by itself: when the only started Spec is cancelled, sent back, or rolled back, the Intent reads `approved` again. A cancelled or rolled-back Spec counts as no progress, because its group is `cancelled`.

### Consequences

- Good, because a board, a tracker mirror, and `aidd status` share one group vocabulary.
- Good, because each closed status can say how it is reopened ([0014](0014-stopped-work-returns-by-approval.md)).
- Bad, because the group `started` holds states that are waiting. Each line says what remains.
- Bad, because a Spec still on its own branch is not on the default branch. There an Intent reads `in_progress` only from the first merge of one of its Specs. The branch and `aidd status --all-branches` show it earlier. No marker is stored when work starts, because the status is read and never stored.

### Reopen when

A tracker that mirrors aidd needs a sixth group.

## More information

[0026](0026-one-word-one-meaning.md) holds the rule that one word has one meaning in every type.
