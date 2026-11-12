# 31. `tracker.update` covers issues only

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. `tracker.update` is not in `schemas/risks.json` yet.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

Writing to an external tracker reaches people and shared state outside the repository. Which tracker objects belong under the `tracker.update` risk action?

## Considered options

- **Cover every tracker write, including pull requests, labels, and projects.** It costs broader patterns in every harness's rule files and overlaps actions such as `pr.merge`.
- **Cover issues only.** It costs leaving pull-request edits, labels, and projects at `allow` unless a team adds a project rule, while keeping one small rule for issue writes.

## Decision outcome

The chosen option is "cover issues only", because issue writes share one clear boundary and pull-request merges already have their own action.

> `tracker.update` asks on every subcommand of the tracker tools' `issue` group that changes an issue, and on calls under `/issues`. Pull requests, labels, and projects are left out by name.

### The case that decided it

A team asked for an ask before an agent closes, edits, or deletes an issue in an external tracker. Naming the `issue` group and `/issues` endpoints keeps the rule predictable without duplicating `pr.merge` or `message.send`.

### Consequences

- Good, because closing, editing, or deleting an issue asks a person before changing shared tracker state.
- Bad, because editing a pull request, label, or project stays `allow` unless a team adds a project rule.

### Reopen when

Teams need built-in asks for pull-request fields, labels, or project boards.

## More information

[0022](0022-the-levels-ask-report-allow.md) explains the risk levels, and [schemas/risks.json](../../schemas/risks.json) holds the built-in rules.
