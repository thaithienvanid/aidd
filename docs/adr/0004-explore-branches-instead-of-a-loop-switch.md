# 0004. Explore branches, instead of a switch that turns the loop off

Date: 2026-10-17. Spec: none: decided before aidd ran its own loop on itself (RATIONALE.md, Known limits).
Decision-makers: the maintainer. Consulted: the security reviews of the guard. Informed: adopters, through METHOD.md §10.4.

## Context and problem statement

People need free work: a spike, a prototype, an experiment. A switch that turned the loop off per worktree split the loop in two, and it failed for the owner on identity. Free work must stay free without ever merging unchecked.

## Considered options

- A per-worktree switch that a person records.
- A config component that turns the loop off for the whole repository.
- A branch namespace, `explore/<topic>`, that the guard frees and the gate refuses.

## Decision outcome

Chosen option: explore branches. What is checked follows the branch, so nothing has to be switched back on.

- On an explore branch the guard allows every edit, and approving, merging, and shipping stay a person's.
- The gate fails any change from one (rule `explore`), so the work is renamed before it is judged like any change.
- Only a person starts or switches to one: the guard denies an agent's git command that could, aliases included.
- `components.loop: false` still turns the loop off for a whole repository.

### Consequences

- Good, because the loop is always on where work can merge, with nothing to forget.
- Bad, because the guard has to read every way git could check a branch out. The oracle below keeps it honest.

### Confirmation

`tests/test_explore_branch.py` pins the rules, and `tests/test_guard_ref_oracle.py` runs generated commands with real git.
