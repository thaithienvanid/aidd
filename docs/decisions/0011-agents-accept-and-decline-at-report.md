# 11. An agent accepts and declines a request at `report`, and a person is always told

Accepted on 2026-11-14. Revised on 2026-11-16: a decline is final, and an agent's decline carries the agent's own name. Decided for 1.0.0, not built yet. `request.accept`, `request.decline`, and `aidd decline` are not in the code yet.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

An agent reads a request and writes a draft from it, or sees that it repeats earlier work. Must a person say yes before the agent takes a request up, and must a person say yes before the agent turns one down? Can a decline be taken back?

## Considered options

- **Accept only on a person's yes.** It costs one ask for each request, and it guards nothing the approval gates do not already guard.
- **A decline asks by default.** It costs a question for each clear duplicate.
- **The agent acts at `report` and tells the person.** It costs a risk of an unseen decline, for a team that reads neither the agent's line nor its commits.
- **A command that takes a decline back (`aidd decline --undo`).** At `report` it lets an agent take out a decline that a person made.

## Decision outcome

The chosen option is "the agent acts at `report` and tells the person", with no way back. Accepting only writes a draft and costs the person nothing. A no that an agent could lift is no decision.

> An agent may accept a request, and may decline a stored one, at `report`, and a person is always told. Only a change outside the repository asks. A decline is final in its place: new words are a new request `from` the declined one.

### The case that decided it

The project owner gave the case: you ask me something that repeats earlier work, and you know it is a duplicate, so you answer that it is a duplicate. In a conversation a decline is that answer and nothing is stored. The invariant is that no request is declined without a person being told, in the conversation, in a commit, or in a handback. A change outside the repository, such as a ticket's state in a tracker, reaches people, so it asks. A person who says "do it after all" gives words of today. They are stored as a new request `from` the declined one, whose line names the decline. An approval that names such a request repeats that line, and `aidd validate` errors on an open item that names a declined request.

### Consequences

- Good, because the Intent's approval and the Spec's approval stay the gates, so nothing is built from a request until a person approves.
- Good, because a decline carries its reason, and a duplicate names the request it repeats.
- Good, because an agent's own decline passes `--by agent:<harness>/<model>`, never a person's name, so no line reads "declined by" a person who did not decline.
- Bad, because a decline at `report` is told and never read, so a team that skips the line and the commit can miss it. A team may set either action to `ask`.
- Bad, because a mistaken decline is put right by a new request, never by an edit.

### Reopen when

A decline is missed in practice, and telling the person is not enough.

## More information

[0008](0008-a-request-stores-no-status.md) says how a request reads. [0012](0012-another-partys-request-always-asks.md) says what a delegated merge does when a change adds or edits a request. [0020](0020-an-approval-names-its-content.md) says how a decline holds.
