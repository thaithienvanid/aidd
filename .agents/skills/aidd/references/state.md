# State

aidd derives every status git or the platform can prove. It stores only a person's decisions and outcomes nobody can observe. `aidd list`, `aidd log`, the guard, and `aidd validate` all read the same derived status. `aidd list` shows all open work and who holds each step (`--agent ROLE`, `--blocked`, `--mine`; `--waiting-on-me` is an Approver's inbox). The Spec's `status` field is an optional cache. You never need to write it. `aidd validate` warns when it disagrees with the derived one. On a platform whose approvals live on the PR/MR, nothing on this machine records them. There, the cache answers whether Spec approval happened: write `ready` in it once it has.

## Spec

<!-- aidd:gen vocab:status -->
| Token | Meaning |
| --- | --- |
| `draft` | Derived: no counted Spec approval of the current hash yet, on a route that needs one; on a route that needs none, no commit in a Task's scope yet. |
| `ready` | Derived: a counted Spec approval of the current hash (a person's `aidd approve spec`, or a gate record that counted one), and no commit in a Task's scope yet. Implementation may start. |
| `in_progress` | Derived: commits on the branch change a Task's scope. |
| `in_review` | Derived: the evidence shows every test command green on head, and the gate record, when there is one, passes or waits only on approvals. It waits for Merge approval. |
| `shipped` | Derived: the approved Spec is on the base branch, merged. The observe window runs now. |
| `done` | Derived: shipped, with no observe block, or with outcome.observe_result pass. Terminal. |
| `rolled_back` | Stored: outcome.rolled_back is true, or outcome.observe_result is fail. Terminal; Learn follows. |
| `cancelled` | Stored: a person set `status: cancelled`, or triage declined the work. Terminal. |
<!-- aidd:end -->

What moves it, and who:

| Trigger | Status after | Who |
| --- | --- | --- |
| a person approves the current hash (`/aidd approve-spec`, or `aidd approve spec` at their terminal) | ready (in progress, if the work already started) | an Approver |
| a commit changes a Task's scope | in_progress | you |
| `aidd test` is green on head (and `aidd gate --record` waits only on approvals) | in_review | the runner |
| a new push after that | in_progress, until the evidence is green again | you |
| the Spec, its tests, or its design change after approval | draft: the approval no longer names the hash | you |
| the branch merges into the base branch | shipped, or done when nothing is to be watched | the platform, or a person's `aidd ship` |
| `aidd observe --write` records pass (the runner records only pass or fail) | done | the runner |
| `aidd observe --write` records fail, or `outcome.rolled_back: true` is recorded | rolled_back | the runner, or the person who ran the rollback |
| a person writes `status: cancelled`, or triage declines the work | cancelled | a person |

**Blocked is a flag, not a status.** A Spec in draft, ready, or in progress is blocked in any of these cases:

- while `blocked_on` names a wait
- while an item it is `blocked_by` has not shipped
- once a Task used its 3 retries

Record `blocked_on`, and remove it when the wait ends. `aidd list` shows the Spec as blocked and names why.

**Tasks** are derived too:

- `todo`: it may start.
- `in_progress`: commits change its scope.
- `done`: its scope changed and the evidence is green on head, the Spec is in review or later, or a person recorded `done: true`.
- `blocked`: the Spec is not approved or is blocked, or a Task it `depends_on` is not done.
- `stopped`: it used its retries, or your latest handoff note stopped while it was in progress.

A Task stores only `retry_count` and `done`, and the hash ignores both.

**Emergency.** An emergency Spec needs no Spec approval. Its step is "restore service" until it ships, then "complete the backfill by `review_due`" until the Spec records `outcome.learn_ref`.

## Epic and Initiative

`draft` until a child starts, then `active`: both derived. `done` and `cancelled` are a person's decision, stored in `status`. `aidd list` suggests closing one when every child is finished. `aidd validate` warns about a done Epic with an open child.

## Proposal

`exploring` until a person records `go_no_go`. Then `no_go`, or `drafting` until `sign_off`, then `signed_off`. All are derived. A person records what happens after: `outcome: {decision: "submitted", by: "@lead", decided_on: "YYYY-MM-DD"}`, then `accepted`, `rejected`, or `withdrawn`. You never write `go_no_go`, `sign_off`, or `outcome`: only a person does.

## What you record

Each `outcome` field has one owner:

| Field | Written by |
| --- | --- |
| `released_on` | the person who released the change, on the day it reached production |
| `observe_result` | `aidd observe <spec> --write`, which the person watching the window runs; never by hand |
| `rolled_back`, `restored_on` | the person who ran the rollback or the fix |
| `result` | the author, from the number you report once the hypothesis date arrives |
| `learn_ref` | you, in Learn: the link to the change that carries the lesson |

You also record:

- `blocked_on` and a Task's `retry_count`
- a `priority` when the team uses it: urgent, high, medium, or low. Unset, it is inherited from the Epic or Initiative. An emergency is urgent.
- an `owner` when the team uses it: the person driving the work, never an agent.

All are outside the Spec hash, so none voids an approval. The gate reads none of them.
