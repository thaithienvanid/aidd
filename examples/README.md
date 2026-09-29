# Examples

Each numbered directory here holds a full verifier context (`context.json`) and the expected decision (`expected.json`). The contexts use shared configs (`_configs/`) and Specs (`_specs/`). `aidd eval examples` runs them all. They are the conformance suite ([`policy/`](policy/) is a Policy example and [`hooks/`](hooks/) a hook example, not cases): a reimplementation of the verifier must agree on every case.

<!-- aidd:gen examples:cases -->
| Case | Title | Decision | What it shows | Mutations |
| --- | --- | --- | --- | --- |
| [`01-minor-docs`](01-minor-docs/) | Minor docs fix | pass | A typo fix: minor route, inline block, one Approver, the repo suite green on head. | 28 |
| [`02-normal-feature`](02-normal-feature/) | Normal feature with a Spec | pass | The worked example: Spec approved by hash, red-then-green proof, Approver is not an author. | 48 |
| [`03-normal-waiting`](03-normal-waiting/) | Normal change waiting | pending | The same change right after the PR opens: the gate waits for Spec approval, tests, and a reviewer. | 0 |
| [`04-major-permission`](04-major-permission/) | Major permission change | pass | An IAM change: major by rule and by type, so it needs the security pool's approval and an observe block. | 1 |
| [`05-emergency-under-freeze`](05-emergency-under-freeze/) | Emergency under a freeze | pass | Production login is broken during a release freeze. Only the emergency route may ship: smoke tests, the commander's approval, and, because the repair touches authentication, the security reviewer who would have reviewed it anyway. | 14 |
| [`06-standard-dependency`](06-standard-dependency/) | Standard dependency bump | pass | A bot's patch bump that matches a configured standard change merges on green tests with no human. | 4 |
| [`07-route-too-low`](07-route-too-low/) | Route too low | fail | Declared minor, but a migration is in the diff: the gate requires major and the data dimension. | 0 |
| [`08-scope-creep`](08-scope-creep/) | Scope creep | fail | The agent also edited payments code outside every Task's scope. | 0 |
| [`09-tests-edited-after-approval`](09-tests-edited-after-approval/) | Tests edited after approval | pending | The test file changed after the Approver signed its hash, so the approval no longer counts. | 0 |
| [`10-bugfix-without-red`](10-bugfix-without-red/) | Bug fix without a red run | fail | The regression test also passes on the unfixed code, so it does not prove the fix. | 0 |
| [`11-solo-major`](11-solo-major/) | Solo major change | pass | A solo developer ships a migration: self-approval is recorded as waived_solo and counts only after the 30-minute cool-off. | 11 |
| [`12-self-approval-blocked`](12-self-approval-blocked/) | Self-approval blocked | pending | The author and the agent's bot account both approved; neither counts under separation of duties, and the agent's platform approval is flagged, because a branch rule's own review count may take it. | 0 |
| [`13-stale-evidence`](13-stale-evidence/) | Stale evidence | pending | Green tests from an earlier commit do not count for the new head. | 0 |
| [`14-raised-to-major`](14-raised-to-major/) | Raised to major | pending | A normal Spec whose diff touches auth code is raised to major, not failed: the major route's rules apply and it waits for a reviewer from the security pool. | 2 |
| [`15-merge-queue`](15-merge-queue/) | Merge-queue entry | pass | The approved feature in a merge queue: approvals stay on the pull request head, the tests re-ran green and red on the merge-group commit, and its tree is exactly that head merged into the commit the entry was built on. | 7 |
<!-- aidd:end -->

`aidd gen-docs` writes this table from each case's `title` and `summary` in its `expected.json`; edit those, not the table.

Each case may also have a `mutations/` folder: JSON files that edit the case's context (`set`, `remove`, `append`, and `replace_text`, whose `old` must occur exactly once, at a JSON pointer) and state the expected result. `aidd eval examples` replays them; they carry the red-team cases in a form any reimplementation can run.

An expectation states the decision, the failed, pending, and warning rules, and `findings`: each finding as `level code`, such as `fail tests.none`. The code says which check fired and why, so a rule that fires for the wrong reason fails its case. Every key is required except a case's `title` and `summary`, which name it in the table above. [`schemas/conformance.schema.json`](../schemas/conformance.schema.json) specifies both file shapes, and a test checks every file against it.

**Running the suite on another verifier.** `aidd eval examples --materialize DIR` writes every case and mutation as `DIR/<name>/context.json`, fully resolved (no shared files, placeholders, or patches left), next to its `expected.json`. Feed each context to your verifier and compare its decision, rules, and codes.

**Comparing a decision.** A case passes when all five keys match:

- `decision` is one of `pass`, `pending`, and `fail`: `fail` when any finding is at level fail, else `pending` when any is pending, else `pass`. Warnings never change it.
- `failed_rules`, `pending_rules`, and `warn_rules` are the rule names with a finding at that level, and `findings` is every finding as `level code`. Each is compared as a list: sorted, with duplicates removed, then equal element by element. Messages and fixes are for people and are never compared.
- A finding the Policy command reports (the context's `policy.findings`) has the rule and the code `policy:<rule>`, such as `fail policy:ticket`, at the level the command chose.
- A context without `now` is judged at the wall clock (only the emergency review window reads it), so every case sets `now`.

**Inputs besides the context.** A verifier also reads bundled data, the same for every case:

- [`schemas/profiles.json`](../schemas/profiles.json): each profile's gates, which a config's `[gates]` table starts from and may only tighten.
- [`schemas/baseline.json`](../schemas/baseline.json): the protected paths (every path a supported agent harness reads as instructions or runs as a hook already merged in by `aidd gen-docs`), the baseline risk rules, and the known agent co-author names the provenance rule reads.
- The schemas the decision validates against: [`context.schema.json`](../schemas/context.schema.json) first (an invalid context is `fail context.invalid` and nothing else), which includes the evidence schema; then `config.schema.json` for the base branch's config, `change-request.schema.json` for the block, `spec.schema.json` for the Spec, and `common.schema.json`, which they share.

[`schemas/roles.json`](../schemas/roles.json) is not an input: it defines the agent team, and no gate rule reads it.

**Schemas and formats.**

- **References.** Every cross-file `$ref` names the target by its `$id` (`urn:aidd:1:common#/$defs/sha`), so register each `schemas/*.schema.json` under its `$id` and a stock JSON Schema 2020-12 validator resolves them; `tests/test_stock_validator.py` checks the corpus that way with python-jsonschema.
- **Formats.** aidd's validator asserts `format: date` and `format: date-time` rather than treating them as annotations: a date-time must parse as ISO 8601 (with `Z` read as `+00:00`), and a date as a real calendar date. A stock validator asserts `format` only when told to (python-jsonschema: a `format_checker`), and the date pattern alone already rejects an impossible month or day, so no case depends on the difference.

**Finding codes.** Every code the verifier can emit, from the rulebook (`src/aidd/rulebook.py`), which `aidd gen-docs` writes here:

<!-- aidd:gen rules:codes -->
| Code | Rule | Fires when |
| --- | --- | --- |
| `context.invalid` | `context` | the context does not validate against context.schema.json (one finding per schema error, up to ten) |
| `internal.crash` | `internal` | the verifier raised an exception; it fails closed |
| `config.bootstrap` | `config` | only the change itself adds the config; an administrator merges the first one |
| `config.invalid` | `config` | the base branch's config (or a parent it extends) does not parse or validate |
| `config.missing` | `config` | no `.aidd/config.toml` on the base branch or in the change |
| `config.newer_version` | `config` | the config declares an `aidd_version` newer than this verifier |
| `config.no_approvers` | `config` | the profile needs `owners.approvers`, and it is empty |
| `config.warning` | `config` | a config setting was ignored, such as a gate looser than the profile allows |
| `change_request.extra_keys` | `change_request` | a block that names a Spec holds keys other than `spec` and `trace_id` |
| `change_request.invalid` | `change_request` | the block does not parse, is not the only one, or does not validate against change-request.schema.json |
| `change_request.no_block` | `change_request` | the PR/MR description has no `toml aidd` block |
| `change_request.standard_by_default` | `change_request` | a bot PR with no block is treated as the standard change class that lists its author |
| `change_request.trace_id_mismatch` | `change_request` | the block's `trace_id` differs from the Spec's |
| `spec.invalid` | `spec` | the Spec does not validate or lint (one finding per error) |
| `spec.missing` | `spec` | normal or major without a `spec` in the block |
| `spec.not_at_head` | `spec` | the named Spec file is not in the head commit |
| `spec.unparsable` | `spec` | the Spec's front matter does not parse |
| `confidence.low` | `confidence` | the change declares confidence `low` |
| `route.raised_to_major` | `route` | a Spec-backed normal change computes major, so it is raised and the major route's rules apply |
| `route.too_low` | `route` | the declared route is below the minimum the paths, dimensions, and type compute |
| `route.undeclared_dimensions` | `route` | `risk.dimensions` lacks a dimension the changed paths imply (fail on an inline block, warn on a Spec) |
| `scope.catch_all` | `scope` | a scope pattern matches every path, so it declares no scope |
| `scope.outside` | `scope` | a changed path (or rename source) is outside every Task's scope and the exempt paths |
| `scope.overlaps_test` | `scope` | an inline block's scope overlaps a test file |
| `scope.test_catch_all` | `scope` | a test-file pattern matches every path, so it names no test file |
| `scope.untouched_task` | `scope` | a Task changed nothing in its scope: the plan and the diff disagree |
| `budget.exceeded` | `budget` | the changed lines exceed the route's `max_changed_lines` |
| `merge_queue.conflict` | `merge_queue` | the approved head does not merge cleanly into the commit the queue entry was built on |
| `merge_queue.diff_mismatch` | `merge_queue` | the merge-group commit's tree is not the approved head merged into the commit it was built on |
| `merge_queue.stacked_unverified` | `merge_queue` | the entry is built on another entry, and the queue is not confirmed to merge only all-green groups |
| `authors.truncated` | `authors` | the platform returned only part of the commit list |
| `authors.unlinked` | `authors` | a commit author maps to no platform account (warn, or fail under `unlinked_authors = fail`) |
| `tests.check_failed` | `tests` | a required status check ended in failure, cancelled, timed_out, or action_required |
| `tests.check_skipped` | `tests` | a required status check was skipped on head |
| `tests.check_waiting` | `tests` | a required status check is still queued, running, or missing |
| `tests.command_mismatch` | `tests` | the runner ran another command than the one declared |
| `tests.duplicate_name` | `tests` | a test name is declared twice, in the config and the Spec |
| `tests.duplicate_result` | `tests` | the evidence holds two results for one test name in one phase |
| `tests.evidence_invalid` | `tests` | the evidence artifact could not be read (the adapter's `invalid` record) |
| `tests.evidence_other_base` | `tests` | the evidence ran against another base commit |
| `tests.evidence_other_head` | `tests` | the evidence is for another head commit |
| `tests.evidence_partial` | `tests` | the evidence comes from `aidd test --changed`, which runs only some commands |
| `tests.evidence_schema` | `tests` | the evidence does not validate against evidence.schema.json |
| `tests.failed` | `tests` | an applicable command did not pass on head |
| `tests.minor_without_suite` | `tests` | a minor change has neither the repository suite nor `evidence.status_checks` |
| `tests.no_evidence` | `tests` | no evidence for the head commit yet |
| `tests.no_op` | `tests` | a test command proves nothing, such as `true`, `echo`, or `sh -c true` |
| `tests.no_result` | `tests` | an applicable command has no result on head |
| `tests.none` | `tests` | the repository and the change declare no tests at all |
| `tests.none_applies` | `tests` | no declared test command's `when_changed` matches the diff |
| `red_green.no_new_behavior` | `red_green` | a feat or fix Spec declares no `new_behavior` test command |
| `red_green.no_red_run` | `red_green` | a `new_behavior` command has no run against the base commit |
| `red_green.passes_on_base` | `red_green` | a `new_behavior` command passes on base, so it proves nothing new |
| `red_green.red_command_mismatch` | `red_green` | the red run used another command than the one declared |
| `red_green.red_not_assertion` | `red_green` | the red run did not fail with a real exit code: a timeout, an error, or exit 126 or 127 |
| `spec_approval.after_implementation` | `spec_approval` | the approved commit already held implementation, so approval came after it began |
| `spec_approval.commit_required` | `spec_approval` | `spec_approval_proof = require`, and no approval names a commit holding only the Spec and its frozen files |
| `spec_approval.missing` | `spec_approval` | no eligible Approver approved the current Spec hash |
| `spec_approval.names_base` | `spec_approval` | an approval names the base commit, which proves no Spec commit |
| `spec_approval.other_tenant` | `spec_approval` | the config names a `tenant`, and a Spec approval came from an identity qualified with another tenant; it never counts |
| `spec_approval.owner_area` | `spec_approval` | an owner area the Spec touches has no Spec approval from its owners |
| `spec_approval.unsigned` | `spec_approval` | locally under `local_approvals = "signed"`, a Spec approval without `verified: true` was dropped |
| `merge_approval.agent_approval` | `merge_approval` | an agent account (`identities.bots`, a baseline `agent_accounts` login such as Copilot's reviewer, a `[bot]` named for an agent) or a bot no pool names approved on the platform; it never counts, and the platform's own review count may |
| `merge_approval.changes_requested` | `merge_approval` | an Approver, specialist reviewer, or path owner's latest review requests changes |
| `merge_approval.missing` | `merge_approval` | fewer eligible, cooled-off approvals on head than `gates.approvals` asks for the route |
| `merge_approval.other_tenant` | `merge_approval` | the config names a `tenant`, and an approval came from an identity qualified with another tenant; it never counts |
| `merge_approval.owner_area` | `merge_approval` | an owner area the diff touches has no approval from its owners |
| `merge_approval.unsigned` | `merge_approval` | locally under `local_approvals = "signed"`, an approval without `verified: true` was dropped |
| `edited_comments.ignored` | `edited_comments` | an edited comment was ignored; approval commands in it do not count |
| `specialist_review.missing` | `specialist_review` | a required specialist pool has too few approvals on head |
| `specialist_review.spec_missing` | `specialist_review` | under `specialist_spec_approval`, a required pool has not approved the Spec hash |
| `specialist_review.unbound` | `specialist_review` | a required specialist pool (and the `security` fallback) is not bound in `owners.reviewers` |
| `policy.break_glass` | `policy` | an emergency ships under a freeze |
| `policy.deny` | `policy` | the Policy command returned deny |
| `policy.freeze` | `policy` | a freeze is on and the route is not emergency |
| `policy.required` | `policy` | the profile requires a bound Policy command on this route, and none is bound |
| `policy.unreachable` | `policy` | the Policy command did not answer, which is deny |
| `policy:<rule>` | `policy:<rule>` | a finding the Policy command reported; its code is its rule, at the level it chose |
| `emergency.backfill_mismatch` | `emergency` | the backfill is not an emergency Spec with the same `review_due` |
| `emergency.backfill_missing` | `emergency` | the backfill Spec is not in the head commit |
| `emergency.backfill_unparsable` | `emergency` | the backfill Spec does not parse |
| `emergency.commander_is_agent` | `emergency` | the incident commander is an agent or bot account |
| `emergency.commander_is_author` | `emergency` | the incident commander is an author of the change |
| `emergency.commander_not_approver` | `emergency` | the incident commander is not an eligible Approver |
| `emergency.commander_pending` | `emergency` | the incident commander has not approved head |
| `emergency.no_block` | `emergency` | route emergency without an emergency block |
| `emergency.review_due_early` | `emergency` | `review_due` is before the day the change opened |
| `emergency.review_due_invalid` | `emergency` | `review_due` is not a calendar date |
| `emergency.review_due_late` | `emergency` | `review_due` is further than `emergency.review_sla_days` from the day the change opened or was last pushed |
| `emergency.would_be_major` | `emergency` | outside an emergency the repair would be major, so the specialist review still applies |
| `observe.missing` | `observe` | the profile's routes need an `observe` block, and the Spec or block has none |
| `provenance.missing_trailer` | `provenance` | under regulated, a non-merge commit has no `Assisted-by` trailer |
| `provenance.no_agent_commit` | `provenance` | `assisted_by` is set, but no commit names an agent |
| `provenance.undeclared_agent` | `provenance` | a commit names an agent, but `assisted_by` is empty |
| `provenance.undeclared_trailer` | `provenance` | a commit trailer names an agent `assisted_by` does not list |
| `standard_change.mismatch` | `standard_change` | the change does not fit its class: paths, authors, line limit, or unsigned commits |
| `standard_change.not_allowed` | `standard_change` | the profile does not allow standard changes |
| `standard_change.unknown_class` | `standard_change` | the block names a standard change class the config lacks |
| `draft.draft` | `draft` | the PR/MR is a draft |
<!-- aidd:end -->

Every level each row of the rulebook (`src/aidd/rulebook.py`) declares is produced by at least one case; `tests/test_conformance_coverage.py` fails when one is not.

See any case's full report, from the repository root:

```sh
PYTHONPATH=src python3 -c "from pathlib import Path; from aidd import evals, report; from aidd.verify import verify; \
ctx,_ = evals.load_example(Path('examples/07-route-too-low')); print(report.text(verify(ctx)))"
```

```text
aidd gate: FAIL
  change 42  head a1a1a1a1a1a1  profile team
  route minor (required major)  type docs  lines 8  files 2
  [FAIL] route: risk.dimensions must include ['data'], which the changed paths imply
        fix: add them to risk.dimensions and run `aidd next` again
  [FAIL] route: declared minor, but the change requires major: rule baseline:migrations matched db/migrations/0042_user_timezone.sql -> at least major; dimensions ['data'] -> major
        fix: set route = "major" and write a Spec
```

Loader conventions in `context.json`:

- `base_config_from`: the config file, relative to the case
- `head_files_from`: repo path → local file
- `spec_hash_of`: substitutes `{{spec_hash}}` in comments
- `{{head}}`: substituted with `head_sha` in comments, review `commit_sha`, and evidence, before any mutation applies (a mutation names the SHA itself)
