# 28. aidd supports OpenCode version 2 and later only

Accepted on 2026-11-14. In force: [SECURITY.md](../../SECURITY.md) and [the guide](../GUIDE.md#every-coding-agent) state it.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

aidd writes a coding agent's ask rules in that agent's own format. OpenCode version 2 reads them from a `permissions` list, and OpenCode version 1 refuses that list. Which versions of OpenCode does aidd support?

## Considered options

- **Version 1 and version 2.** It costs a second format to write, to test for each harness as the project requires, and to keep true in `aidd doctor`.
- **Version 2 and later.** It costs a team on version 1 an upgrade, and `aidd doctor` names an installed version 1 and gives the step.
- **Write no OpenCode rules.** It costs the stop: OpenCode would hold a person's approval by the skill alone.

## Decision outcome

The chosen option is "version 2 and later", because aidd writes one format and tests it, and a version 1 refuses it.

> aidd supports OpenCode version 2 and later. It writes the ask rules in version 2's `permissions` list.

### The case that decided it

The project owner noted that only OpenCode v2 and later is supported. That is already the rule in SECURITY.md and the guide. The case is a team on version 1: the file aidd writes would be refused, so the rules would not exist. A clear refusal and an upgrade step are better than rules that look written and do nothing.

### Consequences

- Good, because the ask rules for OpenCode are one format with one test.
- Bad, because a team on version 1 must install version 2 before aidd's rules apply.

### Reopen when

OpenCode version 1 is still widely used, and a second format is cheap to hold.

## More information

[0002](0002-advise-never-enforce.md) says why aidd leaves the stop to the coding agent.
