# Examples

Each numbered directory here holds a full gate context (`context.json`) and the expected decision (`expected.json`). The contexts use shared configs (`_configs/`) and Specs (`_specs/`). `aidd eval examples` runs them all. They are the conformance suite ([`policy/`](policy/) is a Policy example and [`hooks/`](hooks/) a hook example, not cases): a reimplementation of the gate must agree on every case.

<!-- aidd:gen examples:cases -->
| Case | Title | Decision | What it shows | Mutations |
| --- | --- | --- | --- | --- |
| [`01-minor-docs`](01-minor-docs/) | Minor docs fix | pass | A typo fix: minor route, inline Change Request block, one Approver, the repo suite green on head. | 64 |
| [`02-normal-feature`](02-normal-feature/) | Normal feature with a Spec | pass | The worked example: Spec approved by hash, red-then-green proof, Approver is not an author. | 71 |
| [`03-normal-waiting`](03-normal-waiting/) | Normal change waiting | pending | The same change right after the PR opens: the gate waits for Spec approval, tests, and a reviewer. | 0 |
| [`04-major-permission`](04-major-permission/) | Major permission change | pass | An IAM change: major by rule and by type, so it needs the security pool's approval and an observe block. | 1 |
| [`05-emergency-under-freeze`](05-emergency-under-freeze/) | Emergency under a freeze | pass | Production login is broken during a release freeze. Only the emergency route may merge: smoke tests, the commander's approval, and, because the repair touches authentication, an approval from the security pool, which a major change needs anyway. | 20 |
| [`06-standard-dependency`](06-standard-dependency/) | Standard dependency bump | pass | A bot's patch bump that matches a configured standard change merges on green tests with no human. | 8 |
| [`07-route-too-low`](07-route-too-low/) | Route too low | fail | Declared minor, but a migration is in the diff: the gate requires major and the data dimension. | 1 |
| [`08-scope-creep`](08-scope-creep/) | Scope creep | fail | The agent also edited search code outside every Task's scope. | 3 |
| [`09-tests-edited-after-approval`](09-tests-edited-after-approval/) | Tests edited after approval | pending | The test file changed after the commit the Approver approved, so the approval no longer counts. | 2 |
| [`10-bugfix-without-red`](10-bugfix-without-red/) | Bug fix without a red run | fail | The regression test also passes on the unfixed code, so it does not prove the fix. | 2 |
| [`11-solo-major`](11-solo-major/) | Solo major change | pass | A solo developer lands a migration: self-approval is recorded as waived_solo. | 11 |
| [`12-self-approval-blocked`](12-self-approval-blocked/) | Self-approval blocked | pending | The author and the agent's bot account both approved; neither counts under separation of duties, and the agent's platform approval is flagged, because a branch rule's own review count may take it. | 2 |
| [`13-stale-evidence`](13-stale-evidence/) | Stale evidence | pending | Green tests from an earlier commit do not count for the new head. | 3 |
| [`14-raised-to-major`](14-raised-to-major/) | Raised to major | pending | A normal Spec whose diff touches auth code is raised to major, not failed: the major route's rules apply and it waits for a reviewer from the security pool. | 2 |
| [`15-merge-queue`](15-merge-queue/) | Merge-queue entry | pass | The approved feature in a merge queue: approvals stay on the pull request head, the tests re-ran green and red on the merge-group commit, and its tree is exactly that head merged into the commit the entry was built on. | 7 |
| [`16-spec-phase`](16-spec-phase/) | Spec phase | pending | The draft PR holds only the Spec and its test, which fails on head as it should before Implement: the gate waits for Spec approval, keeps the red and green results as early proof, and asks for no Merge approval yet. | 2 |
| [`17-solo-optional-spec-approval`](17-solo-optional-spec-approval/) | Solo optional Spec approval | pass | Under solo a normal change needs no Spec approval, but one was recorded: it binds the Spec and its tests by hash, and red-then-green becomes required for that Spec. | 3 |
| [`18-linked-docs`](18-linked-docs/) | Linked docs | pass | The Spec links a frozen tech spec: approved with the Spec by hash, allowed outside every Task's scope, and left out of the line budget like a design file, so the 420-line document does not push the change over the normal budget. | 2 |
| [`19-payments-major`](19-payments-major/) | Payments change, security stands in for finance | pass | A refund change routes major by baseline:payments, on the financial dimension, for the finance pool. The config binds only a security pool, so it stands in: its approval on head passes, and a team with no finance reviewer is not deadlocked. | 3 |
| [`20-dependency-raises-route`](20-dependency-raises-route/) | Raised to major by an added dependency | pending | A normal Spec adds the stripe SDK to web/package.json for code in lib/money.ts, outside every folder the built-in rules name. The manifest says what the paths do not: baseline:payments matches the added dependency, so the change is raised to major on the financial dimension and waits for the security pool, which stands in for finance. | 3 |
| [`21-personal-data-raises-route`](21-personal-data-raises-route/) | Raised to major on personal data | pending | A normal Spec adds a preferred name to the customer profile in src/customers/profile.py. baseline:personal-data matches the customers folder, so the change is raised to major on the privacy dimension and waits for the privacy pool, which the security pool stands in for until one is bound. | 3 |
| [`22-boundaries-baseline-raises-route`](22-boundaries-baseline-raises-route/) | Raised to major by the boundary baseline | pending | A normal Spec carves the notifications module out and removes its lines from boundaries-baseline.json. baseline:module-boundaries matches the baseline file, so the change is raised to major and waits for the architecture pool, which the security pool stands in for until one is bound. | 4 |
| [`23-goal-two-specs`](23-goal-two-specs/) | A goal lands two Specs | pass | A goal branch lands SPEC-220 and SPEC-222 in main together (`specs`): each Spec is judged as its own change against the whole diff, with its own approval by hash and its own red-then-green proof, and one Merge approval of the head covers both. | 7 |
| [`24-tests-written-with-the-code`](24-tests-written-with-the-code/) | Tests written with the code | pass | New code with nothing to break (`tests.mode: with_code`): Spec approval binds the Spec and the commands that cover each Acceptance item, not the test file, which changed after it; the test still fails on the base and passes on the head. | 4 |
| [`25-specialist-asked-by-content`](25-specialist-asked-by-content/) | A specialist asked by what the change adds | pending | A normal Spec, approved and green, whose diff adds a line that runs SQL built from an f-string. The repository's raw-sql rule reads the added lines of its Python files and names the data pool, so the change stays normal but waits for a data specialist's approval on head, as a team asks its DBA to look at raw SQL whatever the size of the change. | 4 |
| [`26-audited-normal`](26-audited-normal/) | Audited normal feature | fail | The audited profile on a normal feature: its Policy is bound and allows, and Spec approval names a commit that holds only the Spec and its tests. The Spec declares no observe block, which audited requires on every normal change, so the gate fails. | 2 |
| [`27-goal-one-approval-commit`](27-goal-one-approval-commit/) | A goal lands two Specs | pass | A goal branch lands SPEC-220 and SPEC-222 in main together (`specs`): each Spec is judged as its own change against the whole diff, with its own approval by hash and its own red-then-green proof, and one Merge approval of the head covers both. | 1 |
| [`28-merge-train`](28-merge-train/) | Merge-train entry | pass | The approved feature in a GitLab merge train, behind another entry: approvals stay on the merge request head, the tests re-ran green and red on the entry's commit against the entry ahead, and its tree is exactly that head merged onto the entry ahead. | 4 |
<!-- aidd:end -->

`aidd gen-docs` writes this table from each case's `title` and `summary` in its `expected.json`; edit those, not the table.

Each case may also have a `mutations/` folder: JSON files that edit the case's context (`set`, `remove`, `append`, and `replace_text`, whose `old` must occur exactly once, at a JSON pointer) and state the expected result. `aidd eval examples` replays them; they carry the red-team cases in a form any reimplementation can run.

An expectation states the decision, the failed, pending, and warning rules, and `findings`: each finding as `level code`, such as `fail tests.none`. The code says which check fired and why, so a rule that fires for the wrong reason fails its case. Every key is required except a case's `title` and `summary`, which name it in the table above. [`schemas/conformance.schema.json`](../schemas/conformance.schema.json) specifies both file shapes, and a test checks every file against it.

**Running the suite on another verifier.** `aidd eval examples --write-cases DIR` writes every case and mutation as `DIR/<name>/context.json`, fully resolved (no shared files, placeholders, or patches left), next to its `expected.json`. Feed each context to your verifier and compare its decision, rules, and codes.

**Comparing a decision.** A case passes when all five keys match:

- `decision` is one of `pass`, `pending`, and `fail`: `fail` when any finding is at level fail, else `pending` when any is pending, else `pass`. Warnings never change it.
- `failed_rules`, `pending_rules`, and `warn_rules` are the rule names with a finding at that level, and `findings` is every finding as `level code`. Each is compared as a list: sorted, with duplicates removed, then equal element by element. Messages and fixes are for people and are never compared.
- A finding the Policy command reports (the context's `policy.findings`) has the rule and the code `policy:<rule>`, such as `fail policy:ticket`, at the level the command chose.
- A context without `now` is judged at the wall clock (only the emergency review window reads it), so every case sets `now`.

**Inputs besides the context.** A verifier also reads bundled data, the same for every case:

- [`schemas/profiles.json`](../schemas/profiles.json): each profile's gates, which a config's `gates` mapping starts from and may only tighten. A profile's `limits` are not gates, and no gate rule reads them.
- [`schemas/baseline.json`](../schemas/baseline.json): the protected paths, the baseline risk rules, and the known agent co-author names the provenance rule reads. The protected paths are `protected_paths` and `harness_paths` together. `aidd gen-docs` writes `harness_paths`: every path a supported agent harness reads as instructions or runs as a hook that `protected_paths` does not already cover.
- The schemas the decision validates against. [`context.schema.json`](../schemas/context.schema.json) comes first, and includes the evidence schema: an invalid context is `fail context.invalid` and nothing else. Then come `config.schema.json` for the base branch's config, `change-request.schema.json` for the block, `spec.schema.json` for the Spec, and `common.schema.json`, which they share.

[`schemas/roles.json`](../schemas/roles.json) is not an input: it defines the agent team, and no gate rule reads it.

**Schemas and formats.**

- **References.** Every cross-file `$ref` names the target by its `$id` (`urn:aidd:1:common#/$defs/sha`), so register each `schemas/*.schema.json` under its `$id` and a stock JSON Schema 2020-12 validator resolves them; `tests/test_stock_validator.py` checks the corpus that way with python-jsonschema.
- **Formats.** aidd's validator asserts `format: date` and `format: date-time` rather than treating them as annotations: a date-time must parse as ISO 8601 (with `Z` read as `+00:00`), and a date as a real calendar date. A stock validator asserts `format` only when told to (python-jsonschema: a `format_checker`), and the date pattern alone already rejects an impossible month or day, so no case depends on the difference.

**Finding codes.** Every code the gate can emit, from the rulebook (`src/aidd/gate/rulebook.py`), which `aidd gen-docs` writes here:

<!-- aidd:gen rules:codes -->
| Code | Rule | Fires when |
| --- | --- | --- |
| `context.invalid` | `context` | the context does not validate against context.schema.json (one finding per schema error, up to ten) |
| `internal.crash` | `internal` | the gate raised an exception; it fails closed |
| `config.bootstrap` | `config` | only the change itself adds the config; an administrator merges the first one |
| `config.invalid` | `config` | the base branch's config (or a parent it extends) does not parse or validate |
| `config.missing` | `config` | no `.aidd/config.yaml` on the base branch or in the change |
| `config.newer_version` | `config` | the config declares an `aidd_version` newer than this aidd |
| `config.no_approvers` | `config` | the profile needs `owners.approvers`, and it is empty |
| `config.warning` | `config` | a config setting was ignored, such as a gate looser than the profile allows |
| `change_request.extra_keys` | `change_request` | a block that names a Spec holds keys other than `spec` and `trace_id` |
| `change_request.invalid` | `change_request` | the block does not parse, is not the only one, or does not validate against change-request.schema.json |
| `change_request.several_specs` | `change_request` | there is no Change Request block, and the diff carries several Specs, so the gate cannot tell which one the change is |
| `change_request.standard_by_default` | `change_request` | a bot PR with no block is treated as the standard change class that lists its author |
| `change_request.trace_id_mismatch` | `change_request` | the block's `trace_id` differs from the Spec's |
| `spec.invalid` | `spec` | the Spec does not validate or lint (one finding per error) |
| `spec.missing` | `spec` | normal or major, as the block declares or the gate computes with no block, and no Spec |
| `spec.not_at_head` | `spec` | the named Spec file is not in the head commit |
| `spec.unparsable` | `spec` | the Spec's front matter does not parse |
| `confidence.low` | `confidence` | the change declares confidence `low` |
| `route.config_preferences_only` | `route` | the change edits `.aidd/config.yaml` and sets only preference keys (baseline.json's `config_preference_keys`), so the file does not make it major |
| `route.raised_to_major` | `route` | a Spec-backed normal change computes major, so it is raised and the major route's rules apply |
| `route.too_low` | `route` | the declared route is below the minimum the paths, added dependencies, dimensions, and type compute |
| `route.undeclared_dimensions` | `route` | `risk.dimensions` lacks a dimension the changed paths or added dependencies imply (fail on an inline Change Request block, warn on a Spec) |
| `scope.catch_all` | `scope` | a scope pattern matches every path, so it declares no scope |
| `scope.outside` | `scope` | a changed path (or rename source) is outside every Task's scope and the exempt paths |
| `scope.overlaps_test` | `scope` | an inline Change Request block's scope overlaps a test file |
| `scope.test_catch_all` | `scope` | a test-file pattern matches every path, so it names no test file |
| `scope.untouched_task` | `scope` | a Task changed nothing in its scope: the plan and the diff disagree |
| `changed_lines.over_limit` | `changed_lines` | the changed lines exceed the route's `max_changed_lines` |
| `merge_queue.conflict` | `merge_queue` | the approved head does not merge cleanly into the commit the queue entry was built on |
| `merge_queue.diff_mismatch` | `merge_queue` | the queue entry's commit's tree is not the approved head merged into the commit it was built on |
| `merge_queue.stacked_unverified` | `merge_queue` | the entry is built on another entry, and the queue is not confirmed to merge only all-green groups |
| `authors.truncated` | `authors` | the platform returned only part of the commit list |
| `authors.unlinked` | `authors` | a commit author maps to no platform account (warn, or fail under `unlinked_authors: fail`) |
| `tests.check_failed` | `tests` | a required status check ended in failure, cancelled, timed_out, or action_required |
| `tests.check_skipped` | `tests` | a required status check was skipped on head |
| `tests.check_waiting` | `tests` | a required status check is still queued, running, or missing |
| `tests.command_mismatch` | `tests` | the runner ran another command than the one declared |
| `tests.dirty_tree` | `tests` | `aidd test` ran in a tree with uncommitted changes or untracked files no .gitignore ignores, so its results prove nothing about the head commit |
| `tests.duplicate_name` | `tests` | a test name is declared twice, in the config and the Spec |
| `tests.duplicate_result` | `tests` | the evidence holds two results for one test name in one phase |
| `tests.evidence_invalid` | `tests` | the evidence artifact could not be read (the adapter's `invalid` record) |
| `tests.evidence_other_base` | `tests` | the evidence ran against another base commit |
| `tests.evidence_other_head` | `tests` | the evidence is for another head commit |
| `tests.evidence_partial` | `tests` | the evidence comes from `aidd test --changed`, which runs only some commands |
| `tests.evidence_schema` | `tests` | the evidence does not validate against evidence.schema.json |
| `tests.failed` | `tests` | an applicable command did not pass on head |
| `tests.flaky` | `tests` | a command passed on head only after a retry (`retries`): counted green, and flaky |
| `tests.minor_without_suite` | `tests` | a minor change has neither the repository suite nor `evidence.status_checks` |
| `tests.no_evidence` | `tests` | no evidence for the head commit yet |
| `tests.no_op` | `tests` | a test command proves nothing, such as `true`, `echo`, or `sh -c true` |
| `tests.no_result` | `tests` | an applicable command has no result on head |
| `tests.none` | `tests` | the repository and the change declare no tests at all |
| `tests.none_applies` | `tests` | no declared test command's `when_changed` matches the diff |
| `tests.retries_exceeded` | `tests` | a command ran more times on head than its declared `retries` allow |
| `tests.setup_unfrozen` | `tests` | a changed file configures or runs the tests, and `tests.files` does not list it, so Spec approval does not freeze it |
| `tests.spec_phase` | `tests` | the change is in its Spec phase: it waits for Spec approval and Implement, and its failing tests are early proof |
| `tests.with_code_not_allowed` | `tests` | `tests.mode: with_code`, but the gate computed the major route: the tests must come first |
| `red_green.no_new_behavior` | `red_green` | a feat or fix Spec declares no `new_behavior` test command |
| `red_green.no_red_run` | `red_green` | a `new_behavior` command has no run against the base commit |
| `red_green.passes_on_base` | `red_green` | a `new_behavior` command passes on base, so it proves nothing new |
| `red_green.red_command_mismatch` | `red_green` | the red run used another command than the one declared |
| `red_green.red_not_assertion` | `red_green` | the red run did not fail with a real exit code: a timeout, an error, exit 126 or 127, or pytest's 3 to 5 (internal error, usage error, no tests collected) |
| `red_green.red_retried` | `red_green` | the red run was retried: red runs once, so a flaky test cannot pass for red |
| `spec_approval.after_implementation` | `spec_approval` | the approved commit already held implementation, so approval came after it began |
| `spec_approval.commit_required` | `spec_approval` | `spec_approval_proof: require`, and no approval names a commit holding only the Spec and its frozen files |
| `spec_approval.missing` | `spec_approval` | no eligible Approver approved the Spec as it reads at head |
| `spec_approval.names_base` | `spec_approval` | an approval names the base commit, which proves no Spec commit |
| `spec_approval.other_tenant` | `spec_approval` | the config names a `tenant`, and a Spec approval came from an identity qualified with another tenant; it never counts |
| `spec_approval.owner_area` | `spec_approval` | an owner area the Spec touches has no Spec approval from its owners |
| `spec_approval.unsigned` | `spec_approval` | locally under `local_approvals: signed`, a Spec approval without `verified: true` was dropped |
| `spec_approval.via_app` | `spec_approval` | an `/aidd approve-spec` line was posted through an App for the person it names (GitHub's performed_via_github_app); it never counts |
| `spec_approval.voided` | `spec_approval` | on a route where Spec approval is optional, an eligible Approver recorded one, and the Spec or its tests changed after it |
| `merge_approval.agent_approval` | `merge_approval` | an agent account (`identities.bots`, a baseline `agent_accounts` login such as Copilot's reviewer, a `[bot]` named for an agent) or a bot no pool names approved on the platform; it never counts, and the platform's own review count may |
| `merge_approval.carried` | `merge_approval` | an approval of an earlier head counts for this one: a trivial rebase carried it (the record names both heads) |
| `merge_approval.changes_requested` | `merge_approval` | an Approver, specialist Approver, or path owner's latest review requests changes |
| `merge_approval.missing` | `merge_approval` | fewer eligible approvals on head than `gates.approvals` asks for the route |
| `merge_approval.not_carried` | `merge_approval` | an approval of an earlier head does not carry: the diff differs, the base does not descend, someone new committed, or the approved head is unknown |
| `merge_approval.other_tenant` | `merge_approval` | the config names a `tenant`, and an approval came from an identity qualified with another tenant; it never counts |
| `merge_approval.owner_area` | `merge_approval` | an owner area the diff touches has no approval from its owners |
| `merge_approval.survives_push` | `merge_approval` | the platform keeps approvals when commits are pushed (GitLab's `reset_approvals_on_push` off), so its own approval count can include an older head's; the gate binds a GitLab approval by time |
| `merge_approval.unsigned` | `merge_approval` | locally under `local_approvals: signed`, an approval without `verified: true` was dropped |
| `merge_approval.via_app` | `merge_approval` | an `/aidd approve` line was posted through an App for the person it names (GitHub's performed_via_github_app); it never counts |
| `secrets.added` | `secrets` | an added line of a file has the shape of a secret; the finding names the file and the kind, never the value |
| `edited_comments.ignored` | `edited_comments` | an edited comment was ignored; approval commands in it do not count |
| `specialist_approval.missing` | `specialist_approval` | a required specialist pool has too few approvals on head |
| `specialist_approval.spec_missing` | `specialist_approval` | under `specialist_spec_approval`, a required pool has not approved the Spec hash |
| `specialist_approval.unbound` | `specialist_approval` | a required specialist pool (and the `security` fallback) is not bound in `owners.specialists` |
| `policy.break_glass` | `policy` | an emergency merges under a freeze |
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
| `emergency.incident_missing` | `emergency` | the emergency block names no `incident` (the ticket or page id) |
| `emergency.no_block` | `emergency` | route emergency without an emergency block |
| `emergency.revert` | `emergency` | the repair is an exact revert of a commit merged on the base: the commander's approval alone merges it |
| `emergency.review_due_early` | `emergency` | `review_due` is before the day the change opened |
| `emergency.review_due_invalid` | `emergency` | `review_due` is not a calendar date |
| `emergency.review_due_late` | `emergency` | `review_due` is further than `emergency.review_sla_days` from the day the change opened or was last pushed |
| `emergency.would_be_major` | `emergency` | outside an emergency the repair would be major, so the specialist approval still applies |
| `observe.missing` | `observe` | the profile's routes need an `observe` block, the Spec or block has none, and more than a protected path made the change major |
| `observe.not_applicable` | `observe` | the `observe` block says nothing runs to watch (`not_applicable`), with the reason the Approver weighs |
| `provenance.missing_trailer` | `provenance` | under audited, a non-merge commit has no `Assisted-by` trailer |
| `provenance.no_agent_commit` | `provenance` | `assisted_by` is set, but no commit names an agent |
| `provenance.undeclared_agent` | `provenance` | a commit names an agent, but `assisted_by` is empty |
| `provenance.undeclared_trailer` | `provenance` | a commit trailer names an agent `assisted_by` does not list |
| `standard_change.mismatch` | `standard_change` | the change does not fit its class: paths, authors, line limit, or unsigned commits |
| `standard_change.not_allowed` | `standard_change` | the profile does not allow standard changes |
| `standard_change.unknown_class` | `standard_change` | the block names a standard change class the config lacks |
| `standard_change.update_type` | `standard_change` | a dependency update is bigger than the class's `update_types` allow (unknown counts as major) |
| `explore.branch` | `explore` | the change's head branch is an explore branch (free work that never merges as it is) |
| `draft.is_draft` | `draft` | the PR/MR is a draft |
<!-- aidd:end -->

Every level each row of the rulebook (`src/aidd/gate/rulebook.py`) declares is produced by at least one case; `tests/test_conformance_coverage.py` fails when one is not.

See any case's full report, from the repository root:

```sh
PYTHONPATH=src python3 -c "from pathlib import Path; from aidd import gate; from aidd.evals import examples; \
ctx,_ = examples.load_example(Path('examples/07-route-too-low')); print(gate.decision_text(gate.decide(ctx)))"
```

```text
aidd gate: FAIL
  change 42  head a1a1a1a1a1a1  profile team
  route minor (required major)  type docs  lines 8  files 2
  [FAIL] route: risk.dimensions must include ['data'], which the changed paths imply
        fix: add them to risk.dimensions and run `aidd gate --paths` again
  [FAIL] route: declared minor, but the change requires major: rule baseline:migrations matched db/migrations/0042_user_timezone.sql -> at least major; dimensions ['data'] -> major
        fix: set route = "major" and write a Spec
```

Loader conventions in `context.json`:

- `base_config_from`: the config file, relative to the case
- `head_files_from`: repo path → local file
- `spec_hash_of`: substitutes `{{spec_hash}}` in comments
- `{{head}}`: substituted with `head_sha` in comments, review `commit_sha`, and evidence, before any mutation applies (a mutation names the SHA itself)
