# 20. An approval's commit names the content it approves

Accepted on 2026-11-14. Revised on 2026-11-16: what a squash keeps, and the one place where a commit may hold an edit and a decision. Decided for 1.0.0, not built yet. Today `Approves:` names the item's id and no content, and a commit that edits an item and decides it never holds.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

A person's yes holds by a commit with an `Approved-by:` line and an `Approves:` line. Today the line names the item and not its content. After a rebase, a cherry-pick, or an amend, a changed item can still read as approved. How can a commit say exactly what was approved, and what does a squash do to it?

## Considered options

- **A pointer record of the commit that approves.** It costs a second home outside git, on one clone, and it never reached the code. It was never built.
- **The line names the id git gives the item's file.** It costs two things. An item edited on its branch after the yes asks again before a squash, even for a field an agent may write. Git also indents the two lines in a squash's draft message, so aidd's merge output must place them.
- **Drop the check that the commit changes only the decision, on the default branch.** It costs the guard: one commit there could change an Intent's title and add its approval, and it would hold.

## Decision outcome

The chosen option is "the line names the blob id", because git already computes an id for exact content and aidd adds no hash of its own. The check that the commit changes only the decision stays everywhere but one place.

> A decision holds by the first commit that holds its `at`. That commit's last paragraph carries `Approved-by:` for the same person and `Approves: <item id> <blob id>`. The item's file in that commit is the blob the line names, and the commit changes nothing in the item but the decision's own object. One commit is excused from that last check: a commit on the first-parent chain of `refs/remotes/origin/<default branch>`, which is what a squash leaves there.

### The case that decided it

After a rebase, an amend, or a cherry-pick onto other content, the message still names the earlier content. So the item reads as changed and asks again. Every accident fails closed. A person checks a commit with `git rev-parse <commit>:<path>`, and `git cat-file -p <id>` prints what was approved. A squash replaces the branch's commits with one, so its one commit always brings an item's content and its decision together. Only there can the check be excused.

### Consequences

- Good, because the rebase gap closes in every clone, and the same rule holds a cancellation and a decline with their own lines.
- Bad, because a squash keeps a decision only when the item's file in the squash is the blob decided on. It keeps the item's last decision when its message carries the two lines as its last paragraph. It drops a decision after an edit, even to a kept field, the older of two decisions on one file, and a Spec's approval, because a Spec's file always changes after it.
- Bad, because the excuse reads one local ref, which a command that reads `allow` can move. With no remote, or a remote of another name, no squash carries a decision, so merge with a merge commit or approve again.
- Bad, because the rule in SECURITY.md that says never to rebase or cherry-pick an approval commit changes with it.

### Reopen when

The platforms offer a way to carry a decision across a squash that aidd can read.

## More information

[SECURITY.md](../../SECURITY.md) holds what a hold assumes today, and [0019](0019-one-decision-entity.md) says what a decision is.
