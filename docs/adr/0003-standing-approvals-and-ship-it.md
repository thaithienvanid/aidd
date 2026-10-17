# 0003. A standing approval, and "ship it" as one for a single change

Date: 2026-10-17. Spec: none: decided before aidd ran its own loop on itself (RATIONALE.md, Known limits).
Decision-makers: the maintainer. Consulted: the security reviews of the decision paths. Informed: adopters, through METHOD.md §8.

## Context and problem statement

An approval binds exact content: a Spec's hash, or a head commit. But a person who runs agents does not want to approve every step by hand, or be asked again for each fix the gate asks for. How can a person decide once without an approval that covers more than they decided?

## Considered options

- Ask the person for every Spec approval and every head.
- Let one approval carry to any later head.
- Record a standing decision once, and record each approval it covers as its own record that names it.

## Decision outcome

Chosen option: a standing decision, with each covered approval recorded on its own.

- `approve all` is a standing approval: only a person starts one, it covers the routes it names, and anyone can stop it.
- A typed `ship it` is a standing approval for one change. It covers the head the person saw, and a later fix while the Spec and its tests stay as approved.
- Each approval recorded under either names it in `Aidd-Confirmed-In` (`standing:` or `ship-it:`). So no record claims the person saw a head they did not.
- Neither covers a head the gate still fails on, or a skipped cool-off. A `ship it` ends when its change lands, or after two hours.

### Consequences

- Good, because a person decides once, and every record stays exact.
- Neutral, because on a platform aidd posts each covered review with the person's own token, as they would.
- Bad, because a fix inside the Task scope ships without the person seeing it. `aidd ship` lists those commits, and the gate's checks still hold.

### Confirmation

`tests/test_decide_smoothly.py` and `tests/test_platform_approve.py` pin what each decision covers, what it never covers, and what each record names.
