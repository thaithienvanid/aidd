# 20. An approval's commit names the content it approves

Accepted on 2026-11-14. Decided for 1.0.0, not built yet. Today `Approves:` names the item's id and no content.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

A person's yes holds by a commit with an `Approved-by:` line and an `Approves:` line. Today the line names the item and not its content. After a rebase, a cherry-pick, or an amend, a changed item can still read as approved. How can a commit say exactly what was approved?

## Considered options

- **A pointer record of the commit that approves.** It costs a second home outside git, on one clone, and it never reached the code. It was never built.
- **The line names the id git gives the item's file.** It costs two things. An item edited on its branch after the yes asks again before a squash, even for a field an agent may write. Git also indents the two lines in a squash's draft message, so aidd's merge output must place them.

## Decision outcome

The chosen option is "the line names the blob id", because git already computes an id for exact content and aidd adds no hash of its own.

> A decision holds by the first commit that holds it. That commit's message carries `Approves: <item id> <blob id>`, and the item's file in that commit is the blob the line names.

### The case that decided it

After a rebase, an amend, or a cherry-pick onto other content, the message still names the earlier content. So the item reads as changed and asks again. Every accident fails closed. A person checks a commit with `git rev-parse <commit>:<path>`, and `git cat-file -p <id>` prints what was approved. The id is 40 or 64 hex digits, as the repository's object format says.

### Consequences

- Good, because the rebase gap closes in every clone, and the same rule holds a cancellation and a decline with their own lines.
- Bad, because a squash keeps a decision only when the item's file in the squash is the blob decided on. A commit that both edits and decides holds only on the first-parent chain of `refs/remotes/origin/<default branch>` (with no fallback to a local branch), so a squash carries a decision only there.
- Bad, because the rule in SECURITY.md that says never to rebase or cherry-pick an approval commit changes with it.

### Reopen when

The platforms offer a way to carry a decision across a squash that aidd can read.

## More information

[SECURITY.md](../../SECURITY.md) holds what a hold assumes today, and [0019](0019-one-decision-entity.md) says what a decision is.
