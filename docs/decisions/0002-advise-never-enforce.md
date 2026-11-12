# 2. aidd advises and enforces nothing

Accepted on 2026-11-14. In force.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

aidd computes the route of a change and the level of each action: `allow`, `report`, or `ask`. It could also stop the agent that breaks a level. Should aidd hold the stop itself, or leave it to something else?

## Considered options

- **Enforce.** aidd would run a gate. It costs a second control that every team must trust, and it fails on every coding agent that aidd does not control. A bug in the gate would stop all work.
- **Advise, and rely on stops that already enforce.** The coding agent's own ask rules and the platform's branch protection hold the stop. It costs a gap, because a coding agent with no ask rules has only the skill, and aidd says so.
- **Advise and say nothing about the gap.** It costs trust, because a reader would take advice for a control.

## Decision outcome

The chosen option is "advise, and rely on stops that already enforce", because a tool that enforces nothing cannot fail closed by accident and cannot be talked past.

> aidd advises and enforces nothing. Hard stops come from the coding agent's ask rules, which `aidd init` writes, and from the platform's branch protection.

### The case that decided it

Eight of fourteen supported coding agents have no ask rules. In those, a person's approval is held by the skill alone. An enforcing aidd would promise a stop there that it cannot give. So aidd names each such agent in `aidd doctor` and lists the limit in [SECURITY.md](../../SECURITY.md), and a person decides where the stop is.

### Consequences

- Good, because the advice is deterministic. It calls no model and gives the same answer for the same input.
- Good, because a rule aidd cannot read is an error and never an `allow`.
- Bad, because a team that wants a hard stop must set it up on the platform. aidd does not do it for them.

### Reopen when

A coding agent that matters to adopters offers a stop that aidd could drive and no other tool already gives.

## More information

[Architecture](../architecture/README.md#context-and-scope) names the hard stops.
