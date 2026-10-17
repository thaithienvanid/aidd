# 0001. The gate judges recorded evidence, never the change's own code

Date: 2026-10-17. Spec: none: decided before aidd ran its own loop on itself (RATIONALE.md, Known limits).
Decision-makers: the maintainer. Consulted: the security reviews of each rework. Informed: adopters, through METHOD.md §14.

## Context and problem statement

An agent writes the change, so neither its code nor its words can judge it. Something outside the change must decide whether it may merge, and every CI must be able to run that decision the same way.

## Considered options

- Run the change's tests inside the gate job, with the gate's credentials.
- Read the evidence the test job recorded on the head commit, and read the change itself only as git objects.
- Trust the agent's report of what it ran.

## Decision outcome

Chosen option: read the recorded evidence and the git objects. It is the only option where hostile code in the change never runs with the gate's credentials.

- The gate reads the change as git objects, and its config from the base branch only.
- Evidence counts only as a runner's exit code bound to the head commit, never as prose.
- The gate's rules answer five questions (`rulebook.QUESTIONS`), and one context file holds everything it decides from. So any CI, or another implementation, can run it.

### Consequences

- Good, because a change cannot loosen its own gate, and a pull request's code never runs in the gate job.
- Good, because the conformance suite (`examples/`) proves any implementation decides the same.
- Bad, because hostile test code can make its own tests lie. Spec approval and Merge approval, both a person's, are the control for that.

### Confirmation

`aidd eval examples` runs 25 cases and their 215 mutations, each pinned by a finding code. `tests/test_conformance_coverage.py` fails when a rule's level has no case.
