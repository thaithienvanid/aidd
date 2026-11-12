# 32. The risk rules are data in the shape of authorization rules, and aidd borrows no engine

Accepted on 2026-11-16, for a decision made while aidd was built. In force.
The maintainers decided it while aidd was built, and this record keeps the reasons that the architecture page gave. Every contributor is informed through this record.

## Context and problem statement

aidd gives the level of an action: `allow`, `report`, or `ask`, narrowed by an area, a branch, or a role. The rules need a form, and something must read them. Authorization systems already solve the same problem. Does aidd adopt one of them, or build its own?

## Considered options

- **Rules written in code.** It costs the audit. A person cannot read, diff, or generate documents from a function, and the harness ask rules would need a second copy.
- **A policy engine, such as Cedar's.** It costs a runtime dependency, which the standard-library-only rule forbids, and a policy language that a person must learn to change one level.
- **Data in an authorization system's shape, read by aidd's own small matcher.** It costs the matcher's upkeep, which is `src/aidd/risk/` and its tests.

## Decision outcome

The chosen option is "data in an authorization shape, read by aidd's own matcher". It keeps one owner for each fact and needs no dependency.

> The risk rules are data in `schemas/risks.json`. They take the shape and names of authorization rules, and the `risk` package reads them. aidd borrows no engine.

### The case that decided it

The shape is borrowed. It takes Cedar's principal, action, resource, and context, Google Cloud IAM's dotted permission names, and Kubernetes RBAC's verbs. So an action is `resource.verb`, such as `pr.open`, a form that authorization systems already use. The sources merge in a fixed order, which is `schemas/risks.json`, then the profile, then the `extends` presets, then the config's `risks`. `aidd risk --list` names where each effective rule came from. The same data writes each coding agent's own ask rules in its own format. So no format holds a second copy.

### Consequences

- Good, because `risk` answers from the config and the paths alone. The command line, the MCP server, and the skill's tables read one answer.
- Good, because a rule that aidd cannot read is an error and never an `allow`.
- Bad, because aidd keeps a matcher, with its own tests, where an engine would be someone else's code.
- Bad, because a command pattern is a net, not a control. A script or an alias can reach the same effect, so the platform's branch protection stays the hard stop.

### Reopen when

The rules need a condition that data in this shape cannot state.

## More information

[METHOD.md](../METHOD.md#6-risk-rules) is normative for the rules. [The architecture page](../architecture/README.md#the-risk-rules) says where the code is. [0002](0002-advise-never-enforce.md) says why aidd leaves the stop to others.
