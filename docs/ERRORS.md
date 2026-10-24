# Error codes

Every code aidd shows you is on this page, with what it means and what to do. Each code has its own link, so a gate finding, a step, or a guard denial can point you straight at its row. When you need a longer story, with the symptom and the cause, [Troubleshooting](TROUBLESHOOTING.md) has it for the codes people meet most.

The tables come from the code that emits each code, so they never drift. Don't edit them by hand: `aidd gen-docs` writes them.

<!-- aidd:gen toc -->
- [Finding codes](#finding-codes)
- [Step codes](#step-codes)
- [Guard reason codes](#guard-reason-codes)
- [Exit codes](#exit-codes)
<!-- aidd:end -->

## Finding codes

The gate reports each finding as `rule.reason`, such as `scope.outside`. The code's link is the code with each dot or underscore as a hyphen, such as `#scope-outside`. `aidd gate --explain <rule>` prints the rule, when it holds, and its codes. The rules are grouped by the five questions the gate asks, as [METHOD.md](METHOD.md#7-evidence-and-the-gate) explains.

<!-- aidd:gen errors:findings -->
### Can the gate trust what it reads?

| Code | Rule | Fires when | What to do |
| --- | --- | --- | --- |
| <a id="context-invalid"></a>`context.invalid` | `context` | the context does not validate against context.schema.json (one finding per schema error, up to ten) | fix the adapter that built the context; if aidd built it, report the bug at https://github.com/thaithienvanid/aidd/issues/new?template=bug.yml with the context JSON attached, secrets removed. The gate fails closed until then |
| <a id="internal-crash"></a>`internal.crash` | `internal` | the gate raised an exception; it fails closed | report the bug at https://github.com/thaithienvanid/aidd/issues/new?template=bug.yml with the context JSON attached, secrets removed; the gate fails closed until it is fixed |
| <a id="config-missing"></a>`config.missing` | `config` | no `.aidd/config.yaml` on the base branch or in the change | run `aidd init` on a branch, and an administrator merges its config first |
| <a id="config-bootstrap"></a>`config.bootstrap` | `config` | only the change itself adds the config; an administrator merges the first one | an administrator merges this first config outside the gate; the gate checks every later change |
| <a id="config-invalid"></a>`config.invalid` | `config` | the base branch's config (or a parent it extends) does not parse or validate | fix `.aidd/config.yaml` on the base branch, where `aidd validate` names each error |
| <a id="config-warning"></a>`config.warning` | `config` | a config setting was ignored, such as a gate looser than the profile allows | tighten or remove the setting the warning names in `.aidd/config.yaml`; `aidd validate` lists each one |
| <a id="config-newer-version"></a>`config.newer_version` | `config` | the config declares an `aidd_version` newer than this aidd | run `aidd self-update` for the CLI, then `aidd upgrade --ref <sha> --yes` for the CI pins, as docs/INSTALL.md describes |
| <a id="config-no-approvers"></a>`config.no_approvers` | `config` | the profile needs `owners.approvers`, and it is empty | list the people who approve in `owners.approvers`, or your own login under solo; an empty list means no change can merge: the gate fails closed until you name one |
| <a id="edited-comments-ignored"></a>`edited_comments.ignored` | `edited_comments` | an edited comment was ignored; approval commands in it do not count | post the approval (`/aidd approve-spec` or `/aidd approve-merge`) in a new comment instead of editing one |

### Is the change what it says it is?

| Code | Rule | Fires when | What to do |
| --- | --- | --- | --- |
| <a id="change-request-several-specs"></a>`change_request.several_specs` | `change_request` | there is no Change Request block, and the diff carries several Specs, so the gate cannot tell which one the change is | name the change's Spec (`spec: specs/<ID>.md`) or a goal's Specs (`specs: [...]`) in a block; `aidd describe` prints one |
| <a id="change-request-invalid"></a>`change_request.invalid` | `change_request` | the block does not parse, is not the only one, or does not validate against change-request.schema.json | fix the block so it is the only one and validates; `aidd describe` writes a valid one |
| <a id="change-request-extra-keys"></a>`change_request.extra_keys` | `change_request` | a block that names a Spec holds keys other than `spec` and `trace_id` | keep only `spec` and `trace_id` in the block; the Spec holds the rest |
| <a id="change-request-trace-id-mismatch"></a>`change_request.trace_id_mismatch` | `change_request` | the block's `trace_id` differs from the Spec's | copy the Spec's `trace_id` into the block, or take `trace_id` out of it |
| <a id="change-request-standard-by-default"></a>`change_request.standard_by_default` | `change_request` | a bot PR with no block is treated as the standard change class that lists its author | add a block (`aidd describe` prints one) when the bot's change does not fit that class |
| <a id="spec-missing"></a>`spec.missing` | `spec` | normal or major, as the block declares or the gate computes with no block, and no Spec | write the Spec with `aidd new spec`, and commit it on the branch; the gate finds it in the diff |
| <a id="spec-not-at-head"></a>`spec.not_at_head` | `spec` | the named Spec file is not in the head commit | commit the Spec file at the path the block's `spec` names |
| <a id="spec-unparsable"></a>`spec.unparsable` | `spec` | the Spec's front matter does not parse | fix the Spec, then run `aidd validate` on it until it shows 0 errors |
| <a id="spec-invalid"></a>`spec.invalid` | `spec` | the Spec does not validate or lint (one finding per error) | fix the Spec, then run `aidd validate` on it until it shows 0 errors |
| <a id="confidence-low"></a>`confidence.low` | `confidence` | the change declares confidence `low` | answer the open questions, then run `aidd gate --paths` again |
| <a id="route-too-low"></a>`route.too_low` | `route` | the declared route is below the minimum the paths, added dependencies, dimensions, and type compute | set `route` to what `aidd gate --paths` computes, with a Spec when it needs one |
| <a id="route-raised-to-major"></a>`route.raised_to_major` | `route` | a Spec-backed normal change computes major, so it is raised and the major route's rules apply | meet the major route: approvals from the named specialist pools, and an `observe` block unless only a protected path made it major |
| <a id="route-undeclared-dimensions"></a>`route.undeclared_dimensions` | `route` | `risk.dimensions` lacks a dimension the changed paths or added dependencies imply (fail on an inline Change Request block, warn on a Spec) | add the dimensions `aidd gate --paths` names to `risk.dimensions` |
| <a id="route-config-preferences-only"></a>`route.config_preferences_only` | `route` | the change edits `.aidd/config.yaml` and sets only preference keys (baseline.json's `config_preference_keys`), so the file does not make it major | nothing to do: the Approver reads the preference change at Merge approval |
| <a id="scope-outside"></a>`scope.outside` | `scope` | a changed path (or rename source) is outside every Task's scope and the exempt paths | keep to the scope, or widen the Task's `scope` in the Spec and ask an Approver for Spec approval again |
| <a id="scope-catch-all"></a>`scope.catch_all` | `scope` | a scope pattern matches every path, so it declares no scope | name the files or directories the change touches in its `scope` |
| <a id="scope-test-catch-all"></a>`scope.test_catch_all` | `scope` | a test-file pattern matches every path, so it names no test file | name the test files or directories in `tests.files` |
| <a id="scope-overlaps-test"></a>`scope.overlaps_test` | `scope` | an inline Change Request block's scope overlaps a test file | keep test files out of the block's `scope` |
| <a id="scope-untouched-task"></a>`scope.untouched_task` | `scope` | a Task changed nothing in its scope: the plan and the diff disagree | finish the Task, or remove it from the Spec and ask an Approver for Spec approval again |
| <a id="changed-lines-over-limit"></a>`changed_lines.over_limit` | `changed_lines` | the changed lines exceed the route's `max_changed_lines` | split the change, or list generated files in `changed_lines_exclude_paths` |
| <a id="standard-change-not-allowed"></a>`standard_change.not_allowed` | `standard_change` | the profile does not allow standard changes | take the route `aidd gate --paths` gives, with a Spec when it needs one |
| <a id="standard-change-unknown-class"></a>`standard_change.unknown_class` | `standard_change` | the block names a standard change class the config lacks | set `standard_change` to a class the config lists, or take the route `aidd gate --paths` gives |
| <a id="standard-change-mismatch"></a>`standard_change.mismatch` | `standard_change` | the change does not fit its class: paths, authors, line limit, or unsigned commits | when the change does not fit its class, take the route `aidd gate --paths` gives instead |
| <a id="standard-change-update-type"></a>`standard_change.update_type` | `standard_change` | a dependency update is bigger than the class's `update_types` allow (unknown counts as major) | take the update through a normal change, or ask a person to widen the class's `update_types` in the base branch's config |
| <a id="explore-branch"></a>`explore.branch` | `explore` | the change's head branch is an explore branch (free work that never merges as it is) | rename the branch (`git branch -m <name>`), then open the change from it again: the gate then checks it as it checks any change |
| <a id="draft-is-draft"></a>`draft.is_draft` | `draft` | the PR/MR is a draft | the author marks the PR/MR ready for review |

### Is it proven on this commit?

| Code | Rule | Fires when | What to do |
| --- | --- | --- | --- |
| <a id="tests-spec-phase"></a>`tests.spec_phase` | `tests` | the change is in its Spec phase: it waits for Spec approval and Implement, and its failing tests are early proof | finish the Tasks until the tests pass on head; the route may need a person's Spec approval first |
| <a id="tests-flaky"></a>`tests.flaky` | `tests` | a command passed on head only after a retry (`retries`): counted green, and flaky | fix the flake; `aidd metrics` counts flaky runs |
| <a id="tests-retries-exceeded"></a>`tests.retries_exceeded` | `tests` | a command ran more times on head than its declared `retries` allow | fix the flake, or ask a person to set `retries` on the command in the config |
| <a id="tests-evidence-partial"></a>`tests.evidence_partial` | `tests` | the evidence comes from `aidd test --changed`, which runs only some commands | run `aidd test` without `--changed`; in CI, wait for `aidd-tests` |
| <a id="tests-dirty-tree"></a>`tests.dirty_tree` | `tests` | `aidd test` ran in a tree with uncommitted changes or untracked files no .gitignore ignores, so its results prove nothing about the head commit | add each path the tests, a build, or your computer left, such as a coverage report, a build folder, or .DS_Store, to .gitignore, and commit or stash your own changes, then run `aidd test` again |
| <a id="tests-none"></a>`tests.none` | `tests` | the repository and the change declare no tests at all | name one command that proves today's behavior, in the config's `tests` or the Spec's |
| <a id="tests-minor-without-suite"></a>`tests.minor_without_suite` | `tests` | a minor change has neither the repository suite nor `evidence.status_checks` | bind the repository suite in `.aidd/config.yaml`, or list your CI checks in `evidence.status_checks` |
| <a id="tests-none-applies"></a>`tests.none_applies` | `tests` | no declared test command's `when_changed` matches the diff | widen a command's `when_changed` to cover the diff, or declare a command that runs on every change |
| <a id="tests-duplicate-name"></a>`tests.duplicate_name` | `tests` | a test name is declared twice, in the config and the Spec | rename one of the two commands in `tests`, so each name is declared once across the config and the Spec |
| <a id="tests-no-op"></a>`tests.no_op` | `tests` | a test command proves nothing, such as `true`, `echo`, or `sh -c true` | write a command that fails when the behavior is wrong, in place of the no-op in `tests` |
| <a id="tests-with-code-not-allowed"></a>`tests.with_code_not_allowed` | `tests` | `tests.mode: with_code`, but the gate computed the major route: the tests must come first | set `tests.mode: first` (or remove it), write and commit the tests, and ask an Approver for Spec approval again |
| <a id="tests-no-evidence"></a>`tests.no_evidence` | `tests` | no evidence for the head commit yet | run `aidd test`; in CI, wait for `aidd-tests` |
| <a id="tests-evidence-invalid"></a>`tests.evidence_invalid` | `tests` | the evidence artifact could not be read (the adapter's `invalid` record) | run `aidd-tests` again; if it repeats, fix the test job that writes the artifact |
| <a id="tests-evidence-schema"></a>`tests.evidence_schema` | `tests` | the evidence does not validate against evidence.schema.json | run `aidd test`; in CI, wait for `aidd-tests` |
| <a id="tests-evidence-other-head"></a>`tests.evidence_other_head` | `tests` | the evidence is for another head commit | run `aidd test`; in CI, wait for `aidd-tests` |
| <a id="tests-evidence-other-base"></a>`tests.evidence_other_base` | `tests` | the evidence ran against another base commit | run `aidd test`; in CI, wait for `aidd-tests` |
| <a id="tests-duplicate-result"></a>`tests.duplicate_result` | `tests` | the evidence holds two results for one test name in one phase | run `aidd test` again, so each command has one result in each phase |
| <a id="tests-no-result"></a>`tests.no_result` | `tests` | an applicable command has no result on head | run `aidd test`; in CI, wait for `aidd-tests` |
| <a id="tests-command-mismatch"></a>`tests.command_mismatch` | `tests` | the runner ran another command than the one declared | run the declared command with `aidd test`, or correct the command in the Spec |
| <a id="tests-failed"></a>`tests.failed` | `tests` | an applicable command did not pass on head | fix the change until the command passes, then run `aidd test` again; a wrong Spec goes back to Specify |
| <a id="tests-check-failed"></a>`tests.check_failed` | `tests` | a required status check ended in failure, cancelled, timed_out, or action_required | fix the change until the `evidence.status_checks` check passes in your CI |
| <a id="tests-check-waiting"></a>`tests.check_waiting` | `tests` | a required status check is still queued, running, or missing | wait for the check to finish; if it never starts, add it to your CI or take it out of `evidence.status_checks` |
| <a id="tests-check-skipped"></a>`tests.check_skipped` | `tests` | a required status check was skipped on head | make the check run on this head, or take it out of `evidence.status_checks` |
| <a id="tests-setup-unfrozen"></a>`tests.setup_unfrozen` | `tests` | a changed file configures or runs the tests, and `tests.files` does not list it, so Spec approval does not freeze it | add the file to the Spec's `tests.files`, so Spec approval freezes it with the tests |
| <a id="red-green-no-new-behavior"></a>`red_green.no_new_behavior` | `red_green` | a feat or fix Spec declares no `new_behavior` test command | declare the test in `new_behavior`, write it first, and run `aidd test`, which runs it on base, where it must fail |
| <a id="red-green-no-red-run"></a>`red_green.no_red_run` | `red_green` | a `new_behavior` command has no run against the base commit | run `aidd test` without `--no-red`, so it runs the test on base |
| <a id="red-green-passes-on-base"></a>`red_green.passes_on_base` | `red_green` | a `new_behavior` command passes on base, so it proves nothing new | tighten the test until it fails on base, then run `aidd test` |
| <a id="red-green-red-not-assertion"></a>`red_green.red_not_assertion` | `red_green` | the red run did not fail with a real exit code: a timeout, an error, exit 126 or 127, or pytest's 3 to 5 (internal error, usage error, no tests collected) | make the test fail by an assertion on base, and check its command collects it; then run `aidd test` |
| <a id="red-green-red-command-mismatch"></a>`red_green.red_command_mismatch` | `red_green` | the red run used another command than the one declared | run red again with the declared command (`aidd test` runs it), or correct the command in the Spec |
| <a id="red-green-red-retried"></a>`red_green.red_retried` | `red_green` | the red run was retried: red runs once, so a flaky test cannot pass for red | run red once with `aidd test`, which never retries it |
| <a id="merge-queue-conflict"></a>`merge_queue.conflict` | `merge_queue` | the approved head does not merge cleanly into the commit the queue entry was built on | update the pull request from its base, ask an Approver for Merge approval on the new head, and queue it again (on GitLab, add the merge request to the merge train again) |
| <a id="merge-queue-diff-mismatch"></a>`merge_queue.diff_mismatch` | `merge_queue` | the queue entry's commit's tree is not the approved head merged into the commit it was built on | remove the entry and queue the pull request again from its approved head (on GitLab, remove the merge request from the merge train and add it again); if it repeats, ask an administrator to check the queue |
| <a id="merge-queue-stacked-unverified"></a>`merge_queue.stacked_unverified` | `merge_queue` | the entry is built on another entry, and the queue is not confirmed to merge only all-green groups | ask an administrator to turn on the queue's "Only merge non-failing pull requests", or build one entry at a time |

### Did the right humans approve it?

| Code | Rule | Fires when | What to do |
| --- | --- | --- | --- |
| <a id="spec-approval-missing"></a>`spec_approval.missing` | `spec_approval` | no eligible Approver approved the Spec as it reads at head | a person types `approve <ID>` at the prompt, and aidd records or posts the line for them |
| <a id="spec-approval-voided"></a>`spec_approval.voided` | `spec_approval` | on a route where Spec approval is optional, an eligible Approver recorded one, and the Spec or its tests changed after it | restore the approved Spec and tests, or a person reads the change and types `approve <ID>` again |
| <a id="spec-approval-owner-area"></a>`spec_approval.owner_area` | `spec_approval` | an owner area the Spec touches has no Spec approval from its owners | an owner of each area the Spec touches approves it |
| <a id="spec-approval-commit-required"></a>`spec_approval.commit_required` | `spec_approval` | `spec_approval_proof: require`, and no approval names a commit holding only the Spec and its frozen files | commit the Spec and its tests alone, and an Approver approves that commit |
| <a id="spec-approval-names-base"></a>`spec_approval.names_base` | `spec_approval` | an approval names the base commit, which proves no Spec commit | a person types `approve <ID>` again, so the approval names the commit that holds the Spec |
| <a id="spec-approval-after-implementation"></a>`spec_approval.after_implementation` | `spec_approval` | the approved commit already held implementation, so approval came after it began | commit the Spec and its tests before any implementation, so a person's approval proves it came first |
| <a id="spec-approval-unsigned"></a>`spec_approval.unsigned` | `spec_approval` | locally under `local_approvals: signed`, a Spec approval without `verified: true` was dropped | the approver records it again with git commit signing set up (`aidd approve`), with a key git trusts |
| <a id="spec-approval-other-tenant"></a>`spec_approval.other_tenant` | `spec_approval` | the config names a `tenant`, and a Spec approval came from an identity qualified with another tenant; it never counts | an Approver from the config's `tenant` approves the Spec |
| <a id="spec-approval-via-app"></a>`spec_approval.via_app` | `spec_approval` | an `/aidd approve-spec` line was posted through an App for the person it names (GitHub's performed_via_github_app); it never counts | the approver posts the line themselves, on the platform's web page or with its CLI, never through an App |
| <a id="merge-approval-missing"></a>`merge_approval.missing` | `merge_approval` | fewer eligible approvals on head than `gates.approvals` asks for the route | a human approves the head commit, by typing `land it` at their coding agent's prompt or by approving the PR/MR |
| <a id="merge-approval-owner-area"></a>`merge_approval.owner_area` | `merge_approval` | an owner area the diff touches has no approval from its owners | an owner of each area the diff touches approves head |
| <a id="merge-approval-changes-requested"></a>`merge_approval.changes_requested` | `merge_approval` | an Approver, specialist Approver, or path owner's latest review requests changes | answer the requested changes and push; the reviewer then approves, or dismisses the review |
| <a id="merge-approval-carried"></a>`merge_approval.carried` | `merge_approval` | an approval of an earlier head counts for this one: a trivial rebase carried it (the record names both heads) | a human approves head again if the rebase changed more than the base |
| <a id="merge-approval-not-carried"></a>`merge_approval.not_carried` | `merge_approval` | an approval of an earlier head does not carry: the diff differs, the base does not descend, someone new committed, or the approved head is unknown | a human approves the head commit, by typing `land it` at their coding agent's prompt or by approving the PR/MR |
| <a id="merge-approval-unsigned"></a>`merge_approval.unsigned` | `merge_approval` | locally under `local_approvals: signed`, an approval without `verified: true` was dropped | the approver records it again with git commit signing set up (`aidd approve`), with a key git trusts |
| <a id="merge-approval-other-tenant"></a>`merge_approval.other_tenant` | `merge_approval` | the config names a `tenant`, and an approval came from an identity qualified with another tenant; it never counts | an Approver from the config's `tenant` approves head |
| <a id="merge-approval-agent-approval"></a>`merge_approval.agent_approval` | `merge_approval` | an agent account (`identities.bots`, a baseline `agent_accounts` login such as Copilot's reviewer, a `[bot]` named for an agent) or a bot no pool names approved on the platform; it never counts, and the platform's own review count may | require the aidd/gate status in the branch rules (docs/PLATFORMS.md), and a person approves |
| <a id="merge-approval-via-app"></a>`merge_approval.via_app` | `merge_approval` | an `/aidd approve` line was posted through an App for the person it names (GitHub's performed_via_github_app); it never counts | the approver posts the line themselves, on the platform's web page or with its CLI, never through an App |
| <a id="merge-approval-survives-push"></a>`merge_approval.survives_push` | `merge_approval` | the platform keeps approvals when commits are pushed (GitLab's `reset_approvals_on_push` off), so its own approval count can include an older head's; the gate binds a GitLab approval by time | ask a GitLab administrator to turn on "Remove all approvals when commits are added" in the merge request approval settings |
| <a id="specialist-approval-unbound"></a>`specialist_approval.unbound` | `specialist_approval` | a required specialist pool (and the `security` fallback) is not bound in `owners.specialists` | bind the pool in `owners.specialists`, such as `security: ["@org/security"]` |
| <a id="specialist-approval-missing"></a>`specialist_approval.missing` | `specialist_approval` | a required specialist pool has too few approvals on head | a member of each named pool approves |
| <a id="specialist-approval-spec-missing"></a>`specialist_approval.spec_missing` | `specialist_approval` | under `specialist_spec_approval`, a required pool has not approved the Spec hash | a member of each named pool approves the Spec hash |
| <a id="authors-truncated"></a>`authors.truncated` | `authors` | the platform returned only part of the commit list | the author splits the change, or squashes it below the platform's commit limit |
| <a id="authors-unlinked"></a>`authors.unlinked` | `authors` | a commit author maps to no platform account (warn, or fail under `unlinked_authors: fail`) | link the email to its platform account, list agent emails in `identities.bots`, or rewrite the commits |

### Is it safe to release?

| Code | Rule | Fires when | What to do |
| --- | --- | --- | --- |
| <a id="secrets-added"></a>`secrets.added` | `secrets` | an added line of a file has the shape of a secret; the finding names the file and the kind, never the value | if it is real, take it out of the change and its history, ask its owner to rotate it, and load it from the environment or a secret store |
| <a id="policy-required"></a>`policy.required` | `policy` | the profile requires a bound Policy command on this route, and none is bound | bind `policy.command` in the config |
| <a id="policy-deny"></a>`policy.deny` | `policy` | the Policy command returned deny | change the PR/MR so the Policy allows it, or ask the Policy's owner |
| <a id="policy-freeze"></a>`policy.freeze` | `policy` | a freeze is on and the route is not emergency | wait for the freeze to end; if production is broken and this is the repair, take route `emergency` |
| <a id="policy-break-glass"></a>`policy.break_glass` | `policy` | an emergency merges under a freeze | the commander makes sure the post-incident review covers landing under the freeze |
| <a id="policy-unreachable"></a>`policy.unreachable` | `policy` | the Policy command did not answer, which is deny | fix the Policy command (`policy.command`) or its runner, then run the gate again |
| <a id="policy-rule"></a>`policy:<rule>` | `policy:<rule>` | a finding the Policy command reported; its code is its rule, at the level it chose | what the finding says; without a fix of its own, meet the rule or ask the Policy's owner |
| <a id="emergency-no-block"></a>`emergency.no_block` | `emergency` | route emergency without an emergency block | add an `emergency` block with its five keys to the Change Request block |
| <a id="emergency-incident-missing"></a>`emergency.incident_missing` | `emergency` | the emergency block names no `incident` (the ticket or page id) | set `incident` in the `emergency` block to the ticket or page id |
| <a id="emergency-revert"></a>`emergency.revert` | `emergency` | the repair is an exact revert of a commit merged on the base: the commander's approval alone merges it | the commander approves head; the revert needs no specialist or path-owner review |
| <a id="emergency-review-due-invalid"></a>`emergency.review_due_invalid` | `emergency` | `review_due` is not a calendar date | set `review_due` to a date, such as 2026-11-05 |
| <a id="emergency-review-due-early"></a>`emergency.review_due_early` | `emergency` | `review_due` is before the day the change opened | set `review_due` on or after the day the change opened |
| <a id="emergency-review-due-late"></a>`emergency.review_due_late` | `emergency` | `review_due` is further than `emergency.review_sla_days` from the day the change opened or was last pushed | set `review_due` within `emergency.review_sla_days` of the day the change opened or was last pushed |
| <a id="emergency-backfill-missing"></a>`emergency.backfill_missing` | `emergency` | the backfill Spec is not in the head commit | commit the backfill stub (`aidd new spec <ID> --route emergency`) at the block's `backfill` path, with the same `review_due` |
| <a id="emergency-backfill-unparsable"></a>`emergency.backfill_unparsable` | `emergency` | the backfill Spec does not parse | fix the backfill Spec's front matter, or write it again with `aidd new spec <ID> --route emergency` |
| <a id="emergency-backfill-mismatch"></a>`emergency.backfill_mismatch` | `emergency` | the backfill is not an emergency Spec with the same `review_due` | set the backfill Spec's `route: emergency` and the block's `review_due` |
| <a id="emergency-commander-is-agent"></a>`emergency.commander_is_agent` | `emergency` | the incident commander is an agent or bot account | name the human who runs the incident as its commander |
| <a id="emergency-commander-is-author"></a>`emergency.commander_is_author` | `emergency` | the incident commander is an author of the change | name a commander who did not write the change |
| <a id="emergency-commander-not-approver"></a>`emergency.commander_not_approver` | `emergency` | the incident commander is not an eligible Approver | name a commander listed in `owners.approvers` |
| <a id="emergency-commander-pending"></a>`emergency.commander_pending` | `emergency` | the incident commander has not approved head | the commander approves head |
| <a id="emergency-would-be-major"></a>`emergency.would_be_major` | `emergency` | outside an emergency the repair would be major, so the specialist approval still applies | a member of each named specialist pool approves head |
| <a id="observe-missing"></a>`observe.missing` | `observe` | the profile's routes need an `observe` block, the Spec or block has none, and more than a protected path made the change major | add an `observe` block with `window`, `rollback_trigger`, and a `command` or `signals`, or `not_applicable` with the reason; a change only a protected path made major, such as one to CI checks, needs none |
| <a id="observe-not-applicable"></a>`observe.not_applicable` | `observe` | the `observe` block says nothing runs to watch (`not_applicable`), with the reason the Approver weighs | the Approver weighs the reason; if something runs after release, replace it with `window`, `rollback_trigger`, and a `command` or `signals` |
| <a id="provenance-undeclared-agent"></a>`provenance.undeclared_agent` | `provenance` | a commit names an agent, but `assisted_by` is empty | list each harness/model in `assisted_by` |
| <a id="provenance-undeclared-trailer"></a>`provenance.undeclared_trailer` | `provenance` | a commit trailer names an agent `assisted_by` does not list | list each harness/model in `assisted_by` |
| <a id="provenance-missing-trailer"></a>`provenance.missing_trailer` | `provenance` | under audited, a non-merge commit has no `Assisted-by` trailer | amend each commit with `Assisted-by: <harness>/<model>`, or `Assisted-by: none` when no agent wrote it |
| <a id="provenance-no-agent-commit"></a>`provenance.no_agent_commit` | `provenance` | `assisted_by` is set, but no commit names an agent | add `Assisted-by:` trailers to the agent's commits, or take out `assisted_by` |
<!-- aidd:end -->

## Step codes

`aidd list` and `aidd autopilot next` give each step a code. An agent's step starts one flow, and a person's step starts none, so autopilot asks the person. A step code's link starts with `step-`, such as `#step-spec-spec-approval`.

<!-- aidd:gen errors:steps -->
| Code | Who takes it | What it means | What `aidd autopilot next` runs |
| --- | --- | --- | --- |
| <a id="step-approver-over-limit"></a>`approver.over_limit` | author | an Approver holds more open approval waits than `limits.max_open_per_approver`: finish a review first, or share them | none: a person's step |
| <a id="step-ask-client"></a>`ask.client` | agent | autopilot drafts a proposal for the client goal it was given | `/aidd-team:propose` |
| <a id="step-ask-product"></a>`ask.product` | agent | autopilot plans the goal it was given: an Initiative, its Epics, and Spec stubs | `/aidd-team:plan` |
| <a id="step-backlog-capped"></a>`backlog.capped` | author | aidd read only the first objects in the Specs folder: archive finished Specs to another folder | none: a person's step |
| <a id="step-deprecation-overdue"></a>`deprecation.overdue` | author | a deprecation is past its `sunset`: write the removal Spec that lists it in `removes_deprecations` | none: a person's step |
| <a id="step-epic-close"></a>`epic.close` | author | every child of the Epic is finished: a person records its status `done` (or `cancelled`) on the base branch | none: a person's step |
| <a id="step-epic-launch-spec"></a>`epic.launch_spec` | agent | a flagged Epic is built: write its launch Spec, which turns the flag on; its Merge approval stays the person's | `/aidd-team:specify` |
| <a id="step-flag-overdue"></a>`flag.overdue` | author | a feature flag is past its `cleanup_due`: write the cleanup Spec that lists it in `removes_flags` | none: a person's step |
| <a id="step-goal-land-standing"></a>`goal.land_standing` | agent | a goal is ready to release, and the standing approval covers it: the agent runs `aidd land` on the goal branch | `aidd land` (under the person's standing approval) |
| <a id="step-goal-release"></a>`goal.release` | Approver | a goal is ready to release: it waits for the person's Merge approval of the goal branch's head | none: a person's step |
| <a id="step-initiative-close"></a>`initiative.close` | author | every child of the Initiative is finished: a person records its status `done` (or `cancelled`) on the base branch | none: a person's step |
| <a id="step-knowledge-action"></a>`knowledge.action` | author | a postmortem or retro action that changes the team's knowledge is due: make the change it names | none: a person's step |
| <a id="step-lane-fast"></a>`lane.fast` | agent | the branch's change takes the fast lane (standard or minor): implement it; the gate takes its route from the diff | `/aidd-team:implement` |
| <a id="step-lane-spec"></a>`lane.spec` | agent | the branch's change needs a Spec (normal or major): specify it first | `/aidd-team:specify` |
| <a id="step-learn-retro"></a>`learn.retro` | agent | the retro is due on its cadence: autopilot runs it | `/aidd-team:retro` |
| <a id="step-nothing-matches"></a>`nothing_matches` | author | nothing matches the filters; under `--waiting-on-me`, the step names who aidd took you for, and how to name yourself | none: a person's step |
| <a id="step-nothing-open"></a>`nothing_open` | author | nothing is open: describe the next change to the agent | none: a person's step |
| <a id="step-overlap"></a>`overlap` | author | two open changes change the same code, or freeze the same doc: agree who goes first, and the later one waits with `blocked_by` | none: a person's step |
| <a id="step-overlap-capped"></a>`overlap.capped` | author | aidd checked only some of the other branches for overlaps: delete merged branches so it checks every open one | none: a person's step |
| <a id="step-proposal-accepted"></a>`proposal.accepted` | author | the proposal was accepted: `aidd proposal convert`, then plan the delivery work | none: a person's step |
| <a id="step-proposal-drafting"></a>`proposal.drafting` | agent | the proposal is being drafted: `/aidd-team:propose`, then `aidd validate` | `/aidd-team:propose` |
| <a id="step-proposal-qualifying"></a>`proposal.qualifying` | decision maker | a proposal waits for its go/no-go decision, which its decision maker records | none: a person's step |
| <a id="step-proposal-signed-off"></a>`proposal.signed_off` | author | the proposal is signed off: send it to its addressee, then record `outcome: submitted` | none: a person's step |
| <a id="step-proposal-submitted"></a>`proposal.submitted` | author | the proposal waits for its addressee to decide: record their answer in `outcome` | none: a person's step |
| <a id="step-setup-doctor-fail"></a>`setup.doctor_fail` | author | a setup check fails: `aidd doctor` lists every check and its fix | none: a person's step |
| <a id="step-setup-missing"></a>`setup.missing` | author | aidd is not set up in this repository: run `aidd init`, or ask the agent to install aidd and apply it | none: a person's step |
| <a id="step-spec-backfill"></a>`spec.backfill` | agent | an emergency restored service: complete the backfill Spec and the post-incident review by its `review_due` | `/aidd-team:postmortem` |
| <a id="step-spec-blocked"></a>`spec.blocked` | author | the Spec names a blocker in `blockers`: clear it and remove the entry, or re-plan | none: a person's step |
| <a id="step-spec-blocked-by"></a>`spec.blocked_by` | author | the Spec waits for the work its `blocked_by` relation names, and starts when that work finishes | none: a person's step |
| <a id="step-spec-cancelled"></a>`spec.cancelled` | author | the Spec was cancelled: nothing to do | none: a person's step |
| <a id="step-spec-done"></a>`spec.done` | author | the Spec is done: nothing to do | none: a person's step |
| <a id="step-spec-draft"></a>`spec.draft` | agent | the Spec and its tests are not finished: finish them, `aidd validate` the Spec, and commit | `/aidd-team:specify` |
| <a id="step-spec-emergency"></a>`spec.emergency` | agent | an emergency Spec is open: restore service inside its scope first, then complete the Spec before its `review_due` | `/aidd-team:implement` |
| <a id="step-spec-in-progress"></a>`spec.in_progress` | agent | the Spec is being built: finish its Tasks and get the tests green | `/aidd-team:implement` |
| <a id="step-spec-integrate"></a>`spec.integrate` | agent | a goal's Spec is built and green: `aidd integrate` lands it in the goal branch | `aidd integrate` (under the person's standing approval) |
| <a id="step-spec-integrated"></a>`spec.integrated` | author | the Spec is in its goal branch, and reaches users with the goal's release: nothing to do now | none: a person's step |
| <a id="step-spec-land-standing"></a>`spec.land_standing` | agent | the change waits for Merge approval with no platform, and the standing approval covers it: the agent runs `aidd land` | `aidd land` (under the person's standing approval) |
| <a id="step-spec-landed"></a>`spec.landed` | agent | the Spec landed: watch its observe window with `aidd observe <spec> --write` | `/aidd-team:rollout` |
| <a id="step-spec-merge-approval"></a>`spec.merge_approval` | Approver | the built change waits for a person's Merge approval: they read the report, then type `land it` or approve the PR/MR | none: a person's step |
| <a id="step-spec-merge-approval-standing"></a>`spec.merge_approval_standing` | agent | the standing approval covers Merge approval on a platform: the agent runs `aidd approve merge`, and the PR/MR merges once `aidd/gate` passes | `aidd approve merge` (under the person's standing approval) |
| <a id="step-spec-needs"></a>`spec.needs` | author | the Spec's handoff note asks a person to decide something: write the answer in the Spec or the PR/MR | none: a person's step |
| <a id="step-spec-outcome-due"></a>`spec.outcome_due` | author | the Spec's hypothesis is past due: measure its metric and record `outcome.result` | none: a person's step |
| <a id="step-spec-publish"></a>`spec.publish` | Approver | the change is built and reviewed: it waits for the person to type `publish`, which opens its PR/MR | none: a person's step |
| <a id="step-spec-publish-standing"></a>`spec.publish_standing` | agent | the change is built and reviewed, and agents publish here: the agent runs `aidd publish` | `aidd publish` (under the person's standing approval) |
| <a id="step-spec-ready"></a>`spec.ready` | agent | Spec approval is recorded: implement the Spec inside its Tasks' scope | `/aidd-team:implement` |
| <a id="step-spec-review"></a>`spec.review` | agent | autopilot runs Review on the current head, beside Verify, and it counts once Verify is clean | `/aidd-team:review` |
| <a id="step-spec-rework"></a>`spec.rework` | agent | Verify or Review failed on the current head, or a person said no: the Spec goes back to Implement once | `/aidd-team:implement` |
| <a id="step-spec-rolled-back"></a>`spec.rolled_back` | agent | the change was rolled back: write the postmortem | `/aidd-team:postmortem` |
| <a id="step-spec-spec-approval"></a>`spec.spec_approval` | Approver | the Spec, its tests, and its design wait for a person's Spec approval: they type `approve <ID>` | none: a person's step |
| <a id="step-spec-spec-approval-standing"></a>`spec.spec_approval_standing` | agent | the Spec waits for Spec approval, and the person's standing approval covers it: the agent runs `aidd approve spec` | `aidd approve spec` (under the person's standing approval) |
| <a id="step-spec-task-person"></a>`spec.task_person` | author | a Task is assigned to a person: they do it, then record `done: true` on it | none: a person's step |
| <a id="step-spec-triage"></a>`spec.triage` | triager | an agent suggested this work: a person triages it (accepted, declined, or snoozed) before anyone builds it | none: a person's step |
| <a id="step-spec-verify"></a>`spec.verify` | agent | autopilot runs Verify on the current head, beside Review, before Merge approval | `/aidd-team:verify` |
| <a id="step-wip-over-limit"></a>`wip.over_limit` | author | an owner holds more Specs in progress than `limits.max_in_progress_per_owner`: finish one before starting another | none: a person's step |
<!-- aidd:end -->

## Guard reason codes

When the guard denies a step, its reason names the next step that works, and the guard log records the reason's code. `aidd metrics --guard` counts the denials by code and by role, so you see which ones fire most. A guard code's link starts with `guard-`, such as `#guard-out-of-scope`. [Troubleshooting](TROUBLESHOOTING.md#the-guard-denied-a-step) walks through the common ones.

<!-- aidd:gen errors:guard -->
| Code | What the guard denied | What to do |
| --- | --- | --- |
| <a id="guard-approval-post"></a>`approval_post` | a command carries `/aidd approve`, and it does more than read | leave the line out; the person types `approve <ID>` at the prompt, and aidd posts it as them |
| <a id="guard-approve-or-merge"></a>`approve_or_merge` | an agent ran a command that approves or merges: `aidd approve`, `aidd land`, `gh pr review --approve`, `gh pr merge`, or an API call that does it | stop and tell the person; they type `approve <ID>`, `land it`, or `merge it` at the prompt, or their standing approval covers it |
| <a id="guard-autopilot-session"></a>`autopilot_session` | the command starts or stops autopilot for another session | start and stop autopilot only for this session, with the id the harness gives it |
| <a id="guard-base-branch"></a>`base_branch` | a git command lands work on the base branch, or moves it | work reaches the base branch through `aidd land` once the person types `land it`, or through its PR/MR once they type `publish` |
| <a id="guard-config-invalid"></a>`config_invalid` | `.aidd/config.yaml` does not parse or validate, so no role writes until it is fixed | run `aidd validate`; the person fixes the config in their own session |
| <a id="guard-decision-record"></a>`decision_record` | a command names `refs/aidd/decisions` or the `Aidd-Merge-Approval` trailer, where local approvals are recorded | only read those approvals; the person types the decision, and aidd records it |
| <a id="guard-decision-typed"></a>`decision_typed` | a command types an approval or a decision word into another terminal or program, where it would pass for the person's keyboard | word the message without it; the person types the decision at the prompt, or answers aidd's dialog |
| <a id="guard-decision-unreadable"></a>`decision_unreadable` | a shell write, or a tool with no new text, to a file that holds a person's decision, which the guard cannot read | use the Edit or Write tool, and leave the decision itself to the person |
| <a id="guard-delegate"></a>`delegate` | `agents.delegate` makes the main session hand this edit to an aidd-team role | start the role the denial names, or ask the person to change `agents.delegate` |
| <a id="guard-device-command"></a>`device_command` | an `orca emulator exec` runs a device command its allowlist does not name, a word that is not plain, a word after `emulator exec` that is no flag's value, or a line with a newline or a backtick | type text with `orca emulator type <text>`, run listed commands joined with `&&` inside one `--command`, or ask the person to run it in their own terminal |
| <a id="guard-exploration-decision"></a>`exploration_decision` | an edit adds or changes an exploration's `outcome`, which only a person records | write the evidence, and leave the outcome to the person |
| <a id="guard-frozen-file"></a>`frozen_file` | a test or design file, or a frozen doc, of a Spec whose approval holds: any edit voids the approval | `aidd revise <ID> "<what was wrong>"`, then the file's owner changes it, and the person approves the new hash |
| <a id="guard-git-dir"></a>`git_dir` | an edit or a shell write inside the git directory | run the git or aidd command that changes it |
| <a id="guard-guard-failed"></a>`guard_failed` | the guard could not run git, read the active Spec, or check the held commands, so it denies | run `aidd doctor`, fix what it names, and try again |
| <a id="guard-hard-link"></a>`hard_link` | the file has more than one hard link, so a write changes it under every other name | write a new file instead, or leave it alone |
| <a id="guard-held-command"></a>`held_command` | the command matches a `guard.held_commands` entry, such as a production deploy | ask the person to run it, or to start the session with the entry's `requires` variable set |
| <a id="guard-initiative-decision"></a>`initiative_decision` | an edit adds or changes an Initiative's `go_no_go`, which only a person records | write the rest, and leave the decision to the person |
| <a id="guard-no-active-spec"></a>`no_active_spec` | no active Spec, so the file has no approved scope | start Specify with `aidd new spec` (or `/aidd-team:specify`); on a branch with several Specs, name it `spec/<ID>` or set `AIDD_SPEC` |
| <a id="guard-not-owner"></a>`not_owner` | a test, design, or doc file of the Spec, from a role that does not own it | hand the change to the owner the denial names, such as the verifier for a test file |
| <a id="guard-other"></a>`other` | a deny reason that no reason code names yet | read the reason the guard printed: it names the next step |
| <a id="guard-out-of-scope"></a>`out_of_scope` | the file is outside every Task's scope in the active Spec | add the file to a Task's scope in the Spec, and ask the person to approve it again; or leave the file alone |
| <a id="guard-proposal-decision"></a>`proposal_decision` | an edit adds or changes a proposal's `go_no_go`, `sign_off`, or `outcome`, or an agent ran the command that records one | write the rest; the person types `decide <proposal> go` or `sign off <proposal>` at the prompt |
| <a id="guard-proposal-part"></a>`proposal_part` | a role edits a part of a proposal that another role writes | hand off to the role that writes that part |
| <a id="guard-protected-branch"></a>`protected_branch` | a push rewrites or deletes main, master, trunk, or the default branch | push your own branch without force; a person changes the protected branches |
| <a id="guard-protected-path"></a>`protected_path` | a protected path, such as the config, CI, or agent instructions, with no approved scope that covers it | put it in a Task's scope, and ask the person to approve the Spec; or leave it alone |
| <a id="guard-review-dismissal"></a>`review_dismissal` | an edit adds, changes, or moves a dismissed finding in REVIEW.md | report the finding, and leave its dismissal to the person who decides |
| <a id="guard-role-area"></a>`role_area` | the file is outside the role's write area, or the role is read-only | hand the file to the role the denial names, or to the person when no role writes it |
| <a id="guard-shell-opaque"></a>`shell_opaque` | a shell command runs code the guard cannot read: a command substitution, a shell fed from stdin or a here-document, `source`, `xargs`, or `find -exec` | use the Write or Edit tool, or split it into plain commands |
| <a id="guard-shell-unknown-target"></a>`shell_unknown_target` | a shell write names its file through `$VAR`, a glob, or a patch the guard cannot read | use Write or Edit with a literal path, or a plain command that names the file |
| <a id="guard-shell-unparsed"></a>`shell_unparsed` | the shell check cannot parse the command, such as one with an unbalanced quote, and the profile fails closed | balance the quotes, or put the text in a file |
| <a id="guard-signing-config"></a>`signing_config` | a `git config` command changes commit signing (`gpg.*`, `user.signingkey`) | leave signing to the person; reading it is fine |
| <a id="guard-subagent-read-only"></a>`subagent_read_only` | a subagent that is not an aidd-team role tried to write, or to run a program that is not on the guard's read list: a helper only reads | spawn it as an `aidd-team:<role>` to write or run tests, or hand the work back to the role or the main session |
| <a id="guard-unknown-role"></a>`unknown_role` | the hook names an aidd-team role the team does not have | name a role from the team (`schemas/roles.json`) |
<!-- aidd:end -->

## Exit codes

Every command exits 0 on success. A crash is always 2, never 1, so a script can tell a failed check from a broken run. An exit code's link starts with `exit-`, such as `#exit-3`. [CLI.md](CLI.md#exit-codes) has the same codes by command.

<!-- aidd:gen errors:exit -->
| Code | What it means |
| --- | --- |
| <a id="exit-0"></a>`0` | `gate` (local or `--context`): pass; `gate github`: posted (pass or pending; advisory always); `gate gitlab`: pass (pending with `--pending-ok`; advisory always); `record verify`: the change record holds and is signed (or unsigned with `--allow-unsigned`); everything else: success |
| <a id="exit-1"></a>`1` | `gate` (local or `--context`): fail; `gate github`: fail; `gate gitlab`: fail, pending, or a stale pipeline; `record verify`: it does not hold, its signature does not verify, or it is unsigned; everything else: a check failed |
| <a id="exit-2"></a>`2` | `gate` (local or `--context`): error; `gate github`: error (an `error` status is posted); `gate gitlab`: error; `record verify`: error (no such record); everything else: error |
| <a id="exit-3"></a>`3` | `gate` (local or `--context`): pending |
<!-- aidd:end -->
