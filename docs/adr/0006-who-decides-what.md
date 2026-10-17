# 0006. Who decides what: the person, and the team on evidence

Date: 2026-10-17. Spec: none: decided before aidd ran its own loop on itself (RATIONALE.md, Known limits).
Decision-makers: the maintainer. Consulted: research on mission command, Scrum, separation of duties, and agency client models. Informed: adopters, through METHOD.md §5.2.

## Context and problem statement

A person may want to decide every detail, or set a goal and delegate the rest. An agent that asks every question wastes their time, and one that decides everything takes decisions that are theirs. The line must be the same for every role and every run.

## Considered options

- The person decides everything.
- The team decides everything except approvals.
- A table of decision rights: who decides each kind of decision, on what evidence, and how it is undone.

## Decision outcome

Chosen option: the table, `loop.decision_rights` in `schemas/roles.json`, generated into METHOD.md and TEAM.md.

- The person decides what only a person can: the four decisions, a change order, and an exception.
- The team decides what a standard, the project's rules, or aidd's default settles, on that evidence.
- The lead takes inner decisions only, and never an approval.
- Each decision the team made is shown on the Merge approval page and in the digest, with how to undo it.

### Consequences

- Good, because a person can fully delegate: they set the goal, and the team decides the rest in the open.
- Bad, because a team decision the person disagrees with comes back as a change order, which costs a round.

### Confirmation

`tests/test_team_decisions.py` pins the table, and the digest and the Merge approval page show the decisions.
