# 0005. Autopilot: aidd decides each step, the harness runs it, a person decides

Date: 2026-10-17. Spec: none: decided before aidd ran its own loop on itself (RATIONALE.md, Known limits).
Decision-makers: the maintainer. Consulted: six real runs (AUTOPILOT.md, Real runs). Informed: adopters, through METHOD.md §5.3.

## Context and problem statement

A long run between a person's decisions needs something to choose the next step, and to stop. A model cannot be trusted to judge its own progress, its spend, or when a person must decide.

## Considered options

- Let the model drive the loop by itself.
- An engine that computes the next step from git, under a lease with limits, which the harness runs.
- No autopilot.

## Decision outcome

Chosen option: the engine. `aidd autopilot next` computes one action from git (run a team command, ask a person, or stop), and aidd starts no agent itself.

- A run holds a lease, with a timebox, token and cost caps, a circuit breaker per step, and a stall breaker across the run.
- In Claude Code, spend is measured from the session's own transcripts, never only reported.
- It stops at every person's decision, and the gate on the change stays the control for what merges.

### Consequences

- Good, because the run's limits and stops hold whatever the model says.
- Bad, because it runs in Claude Code only, and depends on its sandbox and permission settings. `aidd doctor --autopilot` checks those.

### Confirmation

`tests/test_autopilot.py` drives the engine with scripted notes. The real runs, and what each found, are in AUTOPILOT.md.
