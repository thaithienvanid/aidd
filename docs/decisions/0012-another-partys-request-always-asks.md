# 12. Work that answers another party's request always asks at its approval

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. The code has no `party` on a request, and the rule is not built.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

A client's words can become a draft, and the draft carries no mark of whose words it came from. A team may delegate Spec approvals and merges. Should work that answers another party's request ask a person at its approval, whatever the dial says?

## Considered options

- **Let the delegate approve it.** It costs the guard: a client's words could become approved work with nobody asked.
- **Ask always, and the delegate defers.** It costs one ask more for each such Spec, even where the team's rule lets Specs go on.
- **Ask only for a client.** It costs the `party` label, which is the agent's reading of whose words these are.

## Decision outcome

The chosen option is "ask always, and the delegate defers", because a draft hides where its words came from.

> A work item that names a request whose `party` is not `owner` always asks at its approval, whatever the project's rule says, and the delegate defers. A change with no Spec that answers another party's request asks at its merge, and the delegate defers there too. A delegated merge also defers (`request_changed`) on any change to a request's file except adding `accepted_in`, `start_on`, `waiting_on`, or an agent's `decline` with no body change, and on any added `aidd validate` error (`validate_errors`).

### The case that decided it

An agent accepts a client's request and drafts INTENT-4. Before a person approves it, the only true sentence is "we have your request and are planning it". So the line reads `accepted as INTENT-4 (draft): nothing is promised until the owner approves INTENT-4`. The same holds for a small fix with no Spec. For requests labelled `party: owner`, a request reaches the default branch only by a person's merge, and so does every later edit, move, or deletion.

### Consequences

- Good, because a client's words never become approved work without a person's yes, and a delegated merge guards every request file.
- Bad, because a team that delegates its approvals gets one ask more for each such Spec, and one at merge for a one-off change that adds or edits a request.
- Bad, because a change that stores no request still passes every request rule.

### Reopen when

A better source for `party` exists than the agent's reading.

## More information

[SECURITY.md](../../SECURITY.md) lists the delegation limits and what holds when a change stores no request.
