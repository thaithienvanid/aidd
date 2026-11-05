# State

A Spec's status lives in its front matter, and you set it as the work moves. Nothing scans for decisions. `aidd status` reads the files and git, and shows each Spec and work item, its status, and its next step (`--mine`, `--json`). `aidd validate` checks the values.

## Spec

<!-- aidd:gen vocab:status -->
| Token | Meaning |
| --- | --- |
| `draft` | Being written, or sent back by a person's yes to `spec.revise`. |
| `ready` | Written. On a route that asks for Spec approval, the agent asked and waits for the answer. |
| `approved` | The person said yes to Spec approval, and the agent set `approved_by` and `approved_at`. Implementation may start. |
| `in_progress` | The agent implements the Spec's Tasks. |
| `in_review` | Every test command is green on head. The change waits for review and Merge approval. |
| `done` | Merged. Terminal, unless the observe window fails and the change rolls back. |
| `rolled_back` | The rollback ran, or the observe window failed (`outcome.rolled_back`, `outcome.observe_result: fail`). Terminal; Learn follows. |
| `cancelled` | A person stopped the work, or triage declined it. Terminal. |
<!-- aidd:end -->

What moves it, and who sets it:

| Moment | Status after | Who |
| --- | --- | --- |
| you start the Spec (`aidd new spec`) | draft | you |
| the Spec validates, and you ask for Spec approval | ready | you |
| the person says yes to Spec approval | approved, with `approved_by` and `approved_at`, committed with an `Approved-by: <person>` trailer | you, from their words |
| the first commit in a Task's scope | in_progress | you |
| Verify and Review are clean on the head, and you ask for Merge approval or open the PR/MR | in_review | you |
| a new push after that | in_progress, until Verify is clean again | you |
| the person says yes to `spec.revise` | draft, with a `revisions` entry: what was wrong, when, and who said yes | you |
| the change is merged into the default branch | done | you, on a local trunk |
| the released change is rolled back | rolled_back | you, from the person's words |
| a person stops the work | cancelled | you, from their words |

On a platform, the merge happens there. `aidd status` sees the Spec on the default branch, and the stored status catches up in the next change that touches the Spec. The `approved_by` note is a record you wrote, never proof. The proof of a merge is the platform's review and git.

Status groups: backlog (draft), unstarted (ready, approved), started (in_progress, in_review), completed (done, rolled_back), and cancelled.

**Blocked is a flag, not a status.** A Spec is blocked while `blockers` names a wait, while an item it is `blocked_by` is not done, or once a Task used its 3 retries. Record `blockers`, and remove it when the wait ends. `aidd status` shows the Spec as blocked and names why.

**Tasks** store only `retry_count` and `done`. Set `done: true` when the Task's scope is finished and its tests are green on the head.

**Emergency.** An emergency Spec needs no Spec approval. Its step is "restore service" until it is merged, then "complete the backfill Spec by `review_due`" until the Spec records `outcome.learn_ref`.

## Epic and Initiative

`draft` until a child starts, then `active`. `done` and `cancelled` are a person's decision: ask, and record it in `status` on their yes. `aidd status` suggests closing one when every child is finished. `aidd validate` warns about a done Epic with an open child.

## Proposal

`qualifying` until a person decides `go_no_go`. Then `no_go`, or `drafting` until `sign_off`, then `signed_off`. Ask for each decision, and record it with the person's name and the date on their yes. A person tells you what happens after, and you record it: `outcome: {decision: "submitted", by: "@lead", decided_on: "YYYY-MM-DD"}`, then `accepted`, `rejected`, or `withdrawn`.

## What you record

Each `outcome` field has one source:

| Field | Comes from |
| --- | --- |
| `released_on` | the day the change reached production |
| `observe_result` | the Spec's observe command over its window, which the SRE runs: pass or fail, never a guess |
| `rolled_back`, `restored_on` | the rollback or the fix, on the person's yes |
| `result` | the number you report once the hypothesis date arrives |
| `learn_ref` | the link to the change that carries the lesson, in Learn |

You also record:

- `blockers` and a Task's `retry_count`
- a `priority` when the team uses it: urgent, high, medium, or low. Unset, it is inherited from the Epic or Initiative. An emergency is urgent.
- an `owner` when the team uses it: the person driving the work, never an agent.
- the interfaces a Spec `provides` and `consumes`.

None of these fields is a change to the approved Spec, so none needs `spec.revise`.
