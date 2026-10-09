# Verify what exists

Load this when the work changes a system that already exists. Do it before you write the scope of a proposal or a change order.

## List the current behaviour

Read the code, and list what the system does now. Write one line for each behaviour that the scope touches.

| Behaviour | Where | Note |
| --- | --- | --- |
| A user can export orders as CSV | `src/orders/export.py:42` | |
| Refunds by card | `src/payments/refund.py:88` | stub: returns success and calls no provider |
| Bulk import | not in code | the client said it exists |
| Dark mode | `web/src/theme.ts:15` | behind the flag `ui.dark_mode`, off in production |

- Give each line a `file:line`, or its stage from [Name the stage](#name-the-stage) when it is not on this commit. Never guess a place.
- Flag a stub: code that exists but does not do the work.
- Flag a hidden feature: one with no menu entry, link, or route that a user can reach.
- Flag a feature behind a flag, and say where the flag is on.
- A behaviour that the client describes and the code does not have is "not in code". Ask the client about it in `questions`.

## Name the stage

Before any claim about a feature, name its stage from evidence:

1. Run `git fetch --all --tags`.
2. Check the stages from the last to the first: deployed, released, merged, on a branch. The feature is at the latest stage that has evidence.
3. Check every branch, not only the default one.

| Stage | Evidence |
| --- | --- |
| Not in code | nothing on any branch (`git log --all -S <name>`), and no open PR/MR |
| Implemented on a branch | the branch (`git branch -a --contains <commit>`), or the open PR/MR |
| Merged | the code on the default branch, with its `file:line` |
| Released | a release tag that contains it (`git tag --contains <commit>`) |
| Deployed | the running version, or the deploy run |

- Never infer a stage from a branch name.
- Write the date of each source document beside the facts you take from it.
- A fact from an old document is not yet a claim. Check it against this table first.

## Use the list

- A proposal statement about the existing system cites its line in this list. A statement with no line is an assumption, and it goes in the assumptions.
- Record each such statement in the proposal's `claims`, with its `file:line` as evidence and `scope = "code"`.
- Keep the list beside the proposal, in its folder. When the code changes before sign-off, read it again.
- The list is a reading of the code on one commit. Write that commit at the top of the list.
