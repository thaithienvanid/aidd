# 0002. A person's local decisions live on their own ref

Date: 2026-10-17. Spec: none: decided before aidd ran its own loop on itself (RATIONALE.md, Known limits).
Decision-makers: the maintainer. Consulted: the security reviews of the guard. Informed: adopters, through METHOD.md §8.

## Context and problem statement

Without GitHub or GitLab, no server holds a person's approval. The record must survive branches and rebases. git must be able to read it, and an agent must not be able to write it.

## Considered options

- A file in the working tree.
- git notes on the approved commits.
- A dedicated ref, `refs/aidd/approvals`, with one commit per decision, signed where the config requires it.

## Decision outcome

Chosen option: the dedicated ref. It is outside every branch, so no merge or rebase touches it, and its history is the audit trail.

- aidd's own commands write it, when a person decides at their own terminal or in their own dialog.
- The guard denies an agent's command that could write it: by name, as bash passes the name on, and under a name the guard cannot read.
- Under `gates.local_approvals: signed`, a decision counts only with an SSH signature from a key the base branch pins.

### Consequences

- Good, because the decision binds exact content (a Spec's hash, a head commit) and is readable with plain git.
- Bad, because the agent runs as the same user as the person. So without signing, the guard is friction, not a boundary. RATIONALE.md says so, and a platform is the stronger home for decisions that matter to other people.

### Confirmation

`tests/test_guard_ref_oracle.py` runs commands with real git and fails on any the guard allowed that wrote the ref. The signed-approval tests pin the signer check.
