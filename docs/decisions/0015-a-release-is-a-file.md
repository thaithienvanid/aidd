# 15. A release is a stored fact in a file

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. There is no release file, no command that writes one, and no `docs/releases/` folder yet. Today a Spec's `outcome` block holds this.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

What is live in an environment, and since when? Today a Spec holds the answer after its merge. A merged Spec is closed work, and a fact about production changes after the merge.

## Considered options

- **A status written to the Spec after the merge.** It costs the rule that closed work is never edited, and it cannot say what each environment holds.
- **Read the platform's deploy history.** It costs the audit: the history lives outside the repository.
- **A release file, written once after the deploy.** It costs one new file type and a command that writes it, and the file is the release step's own account.

## Decision outcome

The chosen option is "a release file", because a fact about production belongs to the release and not to the Spec.

> A release is a file, written once after a deploy, that names an environment, the commit that runs there, the Specs it holds, and the Specs it rolled back. A Spec's status after the merge is read from the default branch and the release files, and never written.

### The case that decided it

A bad release and its rollback on one day are two files, ordered by when users had them. A rollback that changes no commit, such as a flag turned off, lists the Spec under `rolled_back`. The Spec then reads `rolled_back` where users are. Writing that to the merged Spec would edit closed work. Also, "live there since" is a fact about the pair of an environment and a Spec, so it fits no field of the Spec.

### Consequences

- Good, because a release, a rollback, and a redo are new files, so nothing closed is edited.
- Good, because an audit reads who recorded the release and which Specs it held from the repository alone.
- Bad, because nothing proves the deploy happened. The file is the release step's own account.

### Reopen when

A platform gives a signed deploy fact that the repository can hold.

## More information

[0004](0004-traceable-and-auditable.md) states the limits of an audit.
