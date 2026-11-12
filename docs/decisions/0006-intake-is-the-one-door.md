# 6. Intake is the graph's seventh stage and its one door

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. `schemas/roles.json` has no Intake stage yet.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

Words come in from a person, from a client, and from a finished piece of work. Should one stage take every request in, or should each route keep its own door?

## Considered options

- **Each route keeps its own door.** It costs three doors with three trust rules, so a rule for another party's words must be written and kept three times.
- **Intake as a node outside the graph.** It costs the guards: nothing in the graph would run them.
- **Intake as the seventh stage and the one door.** It costs an edge from Learn to Intake, and the emergency route must pass Intake on a person's word alone.

## Decision outcome

The chosen option is "Intake as the seventh stage and the one door", because words from outside become a stored fact in one place, so one set of guards covers them.

> Intake is the graph's seventh stage and its one door. A request enters there, and new work that Learn raises returns there.

### The case that decided it

A client's wish "change how tax is checked" is work and no attack. The agent drafts from it, and a person approves the draft. But a draft carries no mark of whose words it came from. Only at the one door can the agent store the request with its `party`, so that [0012](0012-another-partys-request-always-asks.md) can ask at the approval. Intake is also where the guards for new work run: one open item for each cause, one request for each source link, and a cap on drafts.

### Consequences

- Good, because the trust rule for outside words lives in one place.
- Good, because an emergency still starts on a person's word and passes Intake with no delay.
- Bad, because every route now has one more step in the data, and the picture and the generated blocks change.

### Reopen when

A route appears that cannot pass Intake without losing its speed.

## More information

[METHOD.md](../METHOD.md) holds the stages, and [0009](0009-a-request-is-stored-when-taken-up.md) says when a request is stored.
