# State

Status is derived: the gate and the PR/MR show where a change is. The Spec's `status` field is optional bookkeeping for the humans and tools that read the file; when you write it, use only these tokens and transitions.

<!-- aidd:gen vocab:status -->
| Token | Meaning |
| --- | --- |
| `draft` | Being assessed or specified; nothing approved yet. |
| `ready` | Spec approval: a human approved the Spec hash. Implementation may start. |
| `in_progress` | Tasks are being implemented inside their scope, verified as they go. |
| `in_review` | Tests are green on head; the change waits for Merge approval. |
| `released` | Merged and deployed. The observe window runs now. |
| `done` | The observe window passed, or none was required. Terminal. |
| `rolled_back` | The rollback trigger fired, or a person rolled it back. Terminal; Learn follows. |
| `blocked` | Waiting on blocked_on. |
| `cancelled` | Stopped by a decision, a freeze, or a final reject. Terminal. |
<!-- aidd:end -->

| From | To | When |
| --- | --- | --- |
| draft | ready | Spec approval: an eligible Approver approved the current Spec hash |
| draft | in_progress | the Spec needs no Spec approval (an emergency backfill Spec, or normal under solo) |
| ready | in_progress | Implement starts on the first Task |
| in_progress | draft | the failure is a wrong Spec or a wrong test; Spec approval must hold again |
| in_progress | in_review | every command exits 0 on head, and red-then-green holds |
| in_review | in_progress | a reviewer finds the diff wrong |
| in_review | draft | a reviewer finds the Spec wrong |
| in_review | released | Merge approval holds, the platform merged, and the release interface deployed |
| released | done | the observe window passed, or none was required |
| released | rolled_back | the rollback trigger fired, or a person rolled back |
| any non-terminal | blocked | record blocked_on |
| blocked | the status it left | the blocker cleared |
| any non-terminal | cancelled | freeze, a final reject, or a decision to stop |

A failed gate adds no status. A retry stays in `in_progress`. Initiative and Epic use `draft`, `active`, `blocked`, `done`, and `cancelled`, and they are `done` when every child is terminal.
