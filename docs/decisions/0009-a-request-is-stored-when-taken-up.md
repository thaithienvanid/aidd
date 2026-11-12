# 9. A request is stored when it is taken up

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. The skill does not yet state the rule below.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

A person chats with an agent all day. Few messages are a formal request for work. aidd calls no model, so it cannot sort a conversation. When does a request become a stored fact?

## Considered options

- **Store every message that sounds like a wish.** It costs a classifier that aidd cannot run, and a pile of files that nobody asked for.
- **Store each request on arrival as `pending`, then sort.** It costs a queue to keep, and it is wrong for a pasted request, which is taken up at once.
- **Store it as a consequence of work starting.** It costs a rule that the agent follows by judgement, and a stored request that never exists for talk.

## Decision outcome

The chosen option is "store it as a consequence of work starting", because the work gives the test that the tool cannot.

> A request is stored as a consequence of work starting, never by sorting chat. When the agent is about to write the first draft of a work item, it saves the person's words as the request that the item names, in the same change.

### The case that decided it

"Why is this test slow?" is a question, so nothing is stored. "Fix the typo in the README" routes `minor`, so the commit is the record. "Let staff sign in with a password" routes `major`, so the request file and the Spec go in one change, and the request reads `accepted` from its first commit. A request reads `pending` in three cases only. The person says to save it for later, or an agent saves a batch before it works through it, or the draft that took it up was cancelled.

### Consequences

- Good, because the request and its draft arrive together, and no commit shows a request that nobody took up.
- Good, because a request that waits in another team's tracker stays there. That tool owns the waiting state, and aidd stores it only when an agent takes it up.
- Bad, because a request dropped in the conversation leaves nothing, so no audit sees it. The project owner chose this.

### Reopen when

Teams report lost requests that a stored `pending` would have kept.

## More information

[0008](0008-a-request-stores-no-status.md) says how a stored request reads, and [0010](0010-a-request-has-its-own-file.md) says where it lives.
