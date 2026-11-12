# 21. The decisions parked for 1.1 take their shape now

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. `proposal.approve` and `acceptance.approve` are not in `schemas/risks.json` yet.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

Several decisions had no shape: a proposal's approval to send, the addressee's answer, a postmortem's publication, a change order, a client's acceptance, and a triage of suggested Specs. Do they wait for 1.1, or take their shape in the first release?

## Considered options

- **Wait for 1.1.** It costs a stored shape that changes after the tag, which breaks files people already wrote.
- **Take shape now.** It costs two new actions that ask, `proposal.approve` and `acceptance.approve`, and the largest Tasks of the names work.

## Decision outcome

The chosen option is "take shape now", because an additive change after the tag is cheap and a changed shape is not.

> Every such decision is `{by, at}`, and it gets the hold where a status that lets work go on is read from it. A proposal's approval, a change order's, and an acceptance ask. `triage` goes: a yes to an agent's suggestion is the person's own request.

### The case that decided it

A postmortem's publication moves a Spec to `done` and closes the emergency route, so it needs the hold. A runbook in use and a risk a person accepts get the shape and no hold, because nothing rests on them. A proposal's `answer` records `by` and `at`, where `by` is free words for who answered for the addressee. The answer counts once a person has approved the file again.

### Consequences

- Good, because every decision has one shape before the first release, and a status read from a decision rests on a held fact.
- Bad, because there are two actions more that ask, and the largest Tasks of the renames fall here.
- Bad, because a coding agent that matches a command by its leading words asks at `aidd approve` as today, with the same known gap for a decision typed into a raw commit.

### Reopen when

A decision shape proves too thin, and the fix is a new key that only adds.

## More information

[0019](0019-one-decision-entity.md) defines the one shape.
