# Evidence and the gate

`aidd gate` locally and `aidd gate github|gitlab` in CI run the same rules. In CI, the config comes from the base branch, and every fact comes from the platform: diff, commits, reviews, comments, the test run, and Policy. The `toml aidd` block only says which Spec or inline declaration applies.

Decisions: `pass` (every rule holds), `pending` (waiting on a human or a runner), `fail` (something must change).

<!-- aidd:gen rules:skill -->
| Rule | Holds when | How you satisfy it |
| --- | --- | --- |
| `context` | the adapter's context validates against its schema | report it with the context JSON; the gate fails closed |
| `internal` | the verifier ran without error; any crash fails closed and the gate posts `error` | report it with the context JSON |
| `config` | the base branch has a valid `.aidd/config.toml` (pending when only the change itself adds one, fail when there is none); outside solo, `owners.approvers` is not empty | an administrator merges the first config; set `owners.approvers` |
| `change_request` | exactly one valid `toml aidd` block; with `spec`, only `spec` and `trace_id`; an inline emergency names its `backfill`; a bot PR without a block matches its standard change class | copy `assets/change-request.md`, or run `aidd change` |
| `spec` | normal and major name a Spec that exists at head, validates, and lints | `aidd validate specs/<ID>.md` until 0 errors |
| `confidence` | not `low` | answer the open questions, then run `aidd next` again |
| `route` | the declared route is at least the computed minimum, except that a Spec-backed normal change is raised to major (warn); an inline block declares every implied dimension (a Spec gets a warning) | `aidd next`; write a Spec when the diff needs one |
| `scope` | every changed path (rename sources too) is inside a Task's scope, the Spec, its backfill, a test or design file, or `scope_exempt_paths`; no scope pattern matches every path; a declared inline scope and the test files do not overlap (a minor change that declares no scope takes its changed paths); every Task of a Spec changes something in its scope (warn: the plan and the diff disagree) | keep to the scope; widen the Spec and get Spec approval again; finish or remove a Task that changed nothing |
| `budget` | changed lines are within `max_changed_lines` for the route, excluding `budget_exclude_paths` and, for a Spec, the Spec and its test and design files Spec approval froze (standard uses its class limit; emergency has none) | split the change, or exclude generated files |
| `merge_queue` | for a merge-queue entry (`merge_group` in the context): its commit's tree is exactly the approved head merged into the commit the entry was built on; an entry built on another entry passes only when the queue merges a group once every entry passed | queue the pull request again from its approved head; turn on the queue's "Only merge non-failing pull requests" |
| `authors` | the platform returned the whole commit list (fail); every commit author maps to a platform account, unless the platform itself blocks committers from approving (`unlinked_authors`: warn, fail under regulated) | split or squash the change; link the email, or list agent emails in `identities.bots` |
| `tests` | the repository has tests (a suite, `evidence.status_checks`, or the Spec's); a minor change has the suite or `status_checks`; every applicable command (`when_changed` included) has a green result on this exact head and base, from a test run of the change's own branch, with the declared command; names are unique; every `status_checks` name succeeded on head, from an allowed app and the change's own branch; with `evidence.signer_workflow`, the evidence carries that workflow's attestation; the evidence is not partial (`aidd test --changed`); in a merge queue, the head and base are the merge-group commit and the commit it was built on | `aidd test`; in CI, wait for `aidd-tests` |
| `red_green` | on Spec-backed normal and major: every `new_behavior` command failed on base (a non-zero exit other than 126 or 127; a compile or import error counts) with the declared command, and a feat or fix change has one | write the test first and see it fail on base |
| `spec_approval` | on the profile's routes, an eligible Approver (not an author, except under solo) approved the current Spec hash; each owner area the Spec touches has an approval from its owners; under `spec_approval_proof = require`, the approval names a commit that held only the Spec and its frozen files; on a local context under `gates.local_approvals = "signed"`, only approvals the adapter marked `verified` count (warn when one was dropped); with a `tenant`, an approval by another tenant's identity never counts (warn) | `aidd hash specs/<ID>.md --comment` prints the line; a human posts it |
| `merge_approval` | as many eligible Approvers as the route requires (`gates.approvals`) approved the head commit; each owner area the diff touches has an approval from its owners; no Approver, specialist reviewer, or path owner's latest review requests changes; on a local context under `gates.local_approvals = "signed"`, only approvals the adapter marked `verified` count (warn when one was dropped); an agent account never approves, and its platform approval warns; with a `tenant`, an approval by another tenant's identity never counts (warn) | a human approves the PR/MR on head |
| `edited_comments` | no edited comment was ignored | post a new comment instead of editing one |
| `specialist_review` | major, and emergency when a protected path changes: `specialist_approvals` approvals on head from each pool the reasons name (`owners.reviewers`; an unbound pool falls back to `security`); under `specialist_spec_approval`, each pool also approved the Spec hash | a member of each named pool approves |
| `policy` | Policy allows; a freeze passes only emergency; a required Policy is bound; unreachable is deny | wait for the freeze to end, or bind `policy.command` |
| `policy:<rule>` | each finding the Policy command reports | what the finding says |
| `emergency` | the emergency block is complete; `review_due` falls within `emergency.review_sla_days` (default 2) of the day the change opened or its head was last pushed, whichever is later; the backfill Spec is committed with the same `review_due`; the commander is a human eligible Approver, not an author or agent, and approved the head | fill the block, commit the backfill stub, and ask the commander |
| `observe` | the profile's routes carry an `observe` block | add window, rollback_trigger, and a command or signals |
| `provenance` | `assisted_by` is set whenever a commit names an agent: an `Assisted-by:` trailer, a `Co-authored-by:` agent (the baseline's `agent_coauthors`), or an author in `identities.bots`; under regulated, every non-merge commit carries a trailer (`Assisted-by: none` when no agent wrote it) | amend the commits or the declaration |
| `standard_change` | the class exists and the profile allows it; paths, authors, and the line limit fit; every commit has a platform-verified signature | use another route when it does not fit |
| `draft` | the PR/MR is not a draft | mark it ready for review |
<!-- aidd:end -->

## Approvals

- Merge approval is a platform review (GitHub "Approve", GitLab "Approve") on the current head commit. Under the solo profile only, the author may instead comment `/aidd approve <full head SHA>`, at least the cool-off after the last push on major.
- Spec approval is the comment `/aidd approve-spec <ID> <hash> <sha>` that `aidd hash --comment` prints; the commit at the end lets the gate prove Spec approval came before implementation (required under regulated). It stays valid across implementation commits, because the hash covers only the Spec, its test files, and its design files.
- A command counts only at column 0 of a line of its own, in a comment that was never edited, outside quotes, code, and HTML comments. Never write these commands anywhere on the platform yourself.
- The authors are the PR/MR author plus every commit author and committer. Accounts listed in `identities.bots` are implementers and can never approve. Bots approve only when listed by name.
- A major change also needs an approval from each specialist pool its reasons name (`owners.reviewers`: `security`, `data`, `privacy`, `finance`, `compliance`, or a pool a risk rule names). An unbound pool falls back to `security`; with no pool bound at all, the gate fails and says which pool to bind. Under regulated, each pool also approves the Spec hash.

## Evidence file

`aidd test` writes `evidence.json` (CI uploads it from the runner's temp folder). Every result carries its `command`, `exit`, `status` (passed, failed, timeout, not_started), `phase` (green or red), and log path, and the file is bound to `head_sha` and `base_sha`. Evidence for any other commit does not count. A local run is for you; the gate reads only the artifact of the test workflow named by `evidence.workflow_path` (default `.github/workflows/aidd-tests.yml`), from a run of this change's own branch.
