# State

A Spec's status lives in its front matter, and you set it as the work moves. Nothing scans for decisions. `aidd status` reads the files and git, and shows each Spec and work item, its status, and its next step (`--who`, `--json`). `aidd validate` checks the values.

**Contents**

<!-- aidd:gen toc -->
- [Spec](#spec)
- [Intent](#intent)
- [Proposal](#proposal)
- [What you record](#what-you-record)
<!-- aidd:end -->

## Spec

<!-- aidd:gen vocab:status -->
| Token | Meaning |
| --- | --- |
| `draft` | Being written, or sent back by a person's yes to `spec.revise`. |
| `ready` | Written. On a route that asks for Spec approval, the agent asked and waits for the answer. |
| `approved` | The person said yes to Spec approval, and the agent set `approved_by` and `approved_at`. Implementation may start. |
| `in_progress` | The agent implements the Spec's Tasks. |
| `in_review` | Verify and Review are clean on the head. The change waits for Merge approval. |
| `done` | Merged. Terminal, unless the observe window fails and the change rolls back. |
| `rolled_back` | The rollback ran, or the observe window failed (`outcome.rolled_back`, `outcome.observe_result: fail`). Terminal; Learn follows. |
| `cancelled` | A person stopped the work, or triage declined it. Terminal. |
<!-- aidd:end -->

What moves it. You set each status, from the person's words where a person decides. A row is one move, and `Who` says who makes it: `person` means a person decides, and you record it on their yes. A pair of statuses with no row is no move.

<!-- aidd:gen transitions:spec -->
| From | To | Who | What moves it | Fields set |
| --- | --- | --- | --- | --- |
| new | `draft` | agent | you start the Spec (`aidd new spec`) |  |
| `draft` | `ready` | agent | the Spec validates, and you ask for Spec approval |  |
| `ready` | `approved` | person | the person says yes to Spec approval, and you commit it with an `Approved-by:` trailer of the same value (`references/spec.md`) | `approved_by`, `approved_at` |
| `ready` | `approved` | agent | you say you go on, where `spec.approve` is `report` or `allow`: the Spec is approved, with `approved_at` and no `approved_by`, as under a delegation | `approved_at` |
| `approved` | `in_progress` | agent | the first commit in a Task's scope |  |
| `in_progress` | `in_review` | agent | Verify and Review are clean on the head, and you ask for Merge approval or open the PR/MR |  |
| `in_review` | `in_progress` | agent | a new push after that, until Verify is clean again |  |
| `approved`, `in_progress`, `in_review` | `draft` | person | the person says yes to `spec.revise`, and you record what was wrong, when, and who said yes | `revisions` |
| `in_review` | `done` | person | the change is merged into the default branch, or under `batched` into `intent/<ID>` |  |
| `done` | `rolled_back` | person | the released change is rolled back, on the person's yes |  |
| `draft`, `ready`, `approved`, `in_progress`, `in_review` | `cancelled` | person | a person stops the work, or declines it at triage |  |
<!-- aidd:end -->

On a platform, the merge happens there. `aidd status` sees the Spec on the default branch, and the stored status catches up in the next change that touches the Spec. The proof of a merge is the platform's review and git.

Status groups: backlog (draft), unstarted (ready, approved), started (in_progress, in_review), completed (done, rolled_back), and cancelled.

**Blocked is a flag, not a status.** A Spec is blocked while `waiting_on` names a wait, or once a Task used all its retries. Record `waiting_on`, and remove it when the wait ends.

An item a Spec is `blocked_by` holds Implement, never Specify. A draft or ready Spec keeps its step, with a note such as "Implement waits for SPEC-1". An approved Spec is blocked until that item is done. `aidd status` names why.

**Tasks** store only `retry_count` and `done`. Set `done: true` when the Task's scope is finished and its tests are green on the head.

**Emergency.** An emergency Spec needs no Spec approval. Its step is "restore service" until it is merged, then "complete the backfill Spec by `backfill_due`" until the Spec records `outcome.learn_ref`.

**Stage.** Say a Spec's stage, never its status: `aidd status` gives it, and `references/graph.md` lists the steps of each stage.

## Intent

A draft until a person approves it (`approval`, held by its commit). Its progress is its slices, such as "2 of 9 merged". Closing it, `done` or `cancelled`, is a person's decision: ask, and record it in `status` on their yes. `aidd status` suggests it once every slice is finished.

<!-- aidd:gen transitions:intent -->
| From | To | Who | What moves it | Fields set |
| --- | --- | --- | --- | --- |
| new | `draft` | agent | you write the Intent (`aidd new intent`) |  |
| `draft` | `approved` | person | a person approves it (`aidd approve`, which asks first), and `aidd status` derives it from the approval's hold | `approval` |
| `draft`, `approved` | `active` | agent | a slice starts: its Spec is in progress or later, or it merged, and `aidd status` derives it |  |
| `draft`, `approved`, `active` | `done` | person | a person closes it on their yes, which `aidd status` suggests once every slice is finished |  |
| `done` | `active` | person | a person reopens it, because a slice is not finished |  |
| `draft`, `approved`, `active` | `cancelled` | person | a person stops it, or records `go_no_go: no_go` |  |
<!-- aidd:end -->

## Proposal

`qualifying` until a person decides `go_no_go`. Then `no_go`, or `drafting` until `sign_off`, then `signed_off`. Ask for each decision, and record it with the person's name and the date on their yes. A person tells you what happens after, and you record it: `outcome: {decision: "submitted", by: "@lead", decided_on: "YYYY-MM-DD"}`, then `accepted`, `rejected`, or `withdrawn`.

<!-- aidd:gen transitions:proposal -->
| From | To | Who | What moves it | Fields set |
| --- | --- | --- | --- | --- |
| new | `qualifying` | agent | you start the proposal (`aidd new proposal`) |  |
| `qualifying` | `no_go` | person | a person decides `go_no_go: no_go` | `go_no_go` |
| `qualifying` | `drafting` | person | a person decides `go_no_go: go` | `go_no_go` |
| `drafting` | `signed_off` | person | a person signs the proposal off (`sign_off`) | `sign_off` |
| `signed_off` | `submitted` | person | it is sent, and you record `outcome: submitted` | `outcome` |
| `submitted` | `accepted` | person | the addressee says yes, and you record `outcome: accepted` | `outcome` |
| `submitted` | `rejected` | person | the addressee says no, and you record `outcome: rejected` | `outcome` |
| `qualifying`, `drafting`, `signed_off`, `submitted` | `withdrawn` | person | the proposal is withdrawn, and you record `outcome: withdrawn` | `outcome` |
<!-- aidd:end -->

## What you record

Each `outcome` field has one source:

| Field | Comes from |
| --- | --- |
| `released_on` | the day the change reached production |
| `observe_result` | the Spec's observe command over its window, which the SRE runs: pass or fail, never a guess |
| `rolled_back`, `restored_on` | the rollback or the fix, on the person's yes |
| `hypothesis_result` | the number you report once the hypothesis date arrives |
| `learn_ref` | the link to the change that carries the lesson, in Learn |

You also record:

- `waiting_on` and a Task's `retry_count`
- a `priority` when the team uses it: urgent, high, medium, or low. Unset, it is medium. An emergency is urgent.
- an `owner` when the team uses it: the person driving the work, never an agent.
- the interfaces a Spec `provides` and `consumes`.

None of these fields is a change to the approved Spec, so none needs `spec.revise`.
