# 12. Work that answers another party's request always asks at its approval

Accepted on 2026-11-14. Revised on 2026-11-16: what a delegated change rests on when its own branch stored the request. Decided for 1.0.0, not built yet. The code has no `party` on a request and no `request_changed` defer. `validate_errors` defers today for a Spec's own errors only.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

A client's words can become a draft, and the draft carries no mark of whose words it came from. A team may delegate Spec approvals and merges. Should work that answers another party's request ask a person at its approval, whatever the dial says? And with both gates delegated, what may a merge rest on when the change's own branch stored the request?

## Considered options

- **Let the delegate approve it.** It costs the guard: a client's words could become approved work with nobody asked.
- **Ask always, and the delegate defers.** It costs one ask more for each such Spec, even where the team's rule lets Specs go on.
- **Ask only for a client.** It costs the `party` label, which is the agent's reading of whose words these are.
- **Show the delegate the request, and let it judge whose words they are.** It costs the guard, because no reader can tell whose words a text is.
- **A person's merge first.** It costs one ask at the merge for each one-off Spec that brings its own request.

## Decision outcome

The chosen option is "ask always, and the delegate defers", with "a person's merge first" for a request that a change's own branch stores. A draft hides where its words came from, and so does a label that the checked agent writes.

> A work item that names a request whose `party` is not `owner` always asks at its approval, whatever the project's rule says, and the delegate defers. A change with no Spec that answers another party's request asks at its merge, and the delegate defers there too. A delegated merge also defers (`request_changed`) on any change to a request's file, be it an add, an edit, a move, or a deletion. One change passes: its body is the same, and its front matter only gains `accepted_in`, `start_on`, `waiting_on`, or an agent's own `decline`. It defers on any `aidd validate` error that the change adds (`validate_errors`).

### The case that decided it

An agent accepts a client's request and drafts INTENT-4. Before a person approves it, the only true sentence is "we have your request and are planning it". So the line reads `accepted as INTENT-4 (draft): nothing is promised until the owner approves INTENT-4`. A read of the design ran the other case: both gates delegated, and a branch that adds a request labelled `party: owner` whose words came from outside. The delegate check read `eligible`, because it takes a request only as the default branch holds it. So a request reaches the default branch only by a person's merge, and so does every later change to it. A request's file is any file whose front matter says `type: request`, wherever it lies.

### Consequences

- Good, because a client's words never become approved work without a person's yes, and a delegated merge guards every request file.
- Bad, because a team that delegates its approvals gets one ask more for each such Spec, and one at merge for a one-off change that adds or edits a request. A minor fix, work under an approved Intent, and the team profile get none.
- Bad, because a change that stores no request still passes every request rule. With both gates delegated, outside words can become a merged change with nobody asked, so a team that takes such words keeps the merge with a person.

### Reopen when

A better source for `party` exists than the agent's reading.

## More information

[SECURITY.md](../../SECURITY.md) lists the delegation limits. Its sentence on a change that stores no request is decided for 1.0.0 and not written there yet.
