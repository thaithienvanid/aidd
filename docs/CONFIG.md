# Config reference

The complete reference for `.aidd/config.toml`: every top-level key, then every table field by field. The tables are generated from `schemas/config.schema.json`, which is the source of truth. Check a config with `aidd validate .aidd/config.toml`, and the whole wiring with `aidd doctor`.

The gate always reads the config from the base branch, never from the change, and every file under `.aidd/` is a protected path, so a config change is itself a major change ([METHOD.md §6](METHOD.md#6-routes)).

A minimal config:

```toml
aidd_version = "1.0.0"
profile = "team"

[owners]
approvers = ["@your-org/leads"]
reviewers = { security = ["@your-org/security"] }

[[tests]]
name = "unit"
command = ["npm", "test"]
```

## Contents

- [Top-level keys](#top-level-keys), and [parents, presets, and locks](#parents-presets-and-locks)
- People: [`[owners]`](#owners), [`[[owners.paths]]`](#ownerspaths), [`mission`, `goal`, and `[agents]`](#mission-goal-and-agents), and [`[[standards]]`](#standards)
- [`extends`](#extends) and [`[targets]`](#targets)
- Proof: [`[[tests]]`](#tests), [`[policy]`](#policy), [`[observe]`](#observe), and [`[evidence]`](#evidence)
- Rules: [`[gates]`](#gates), [`[[risk_rules]]`](#risk_rules), [`[[standard_changes]]`](#standard_changes), [`[identities]`](#identities), and [`[emergency]`](#emergency)
- Agent sessions: [`[guard]`](#guard), [`[[guard.gated_commands]]`](#guardgated_commands), and [`[hooks]`](#hooks)

## Top-level keys

<!-- aidd:gen fields:config -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `aidd_version` | string | yes | The aidd release this record conforms to; the method and the toolkit share one version. |
| `profile` | `profile` | yes | Conformance profile. Each one is stricter than the one before. |
| `mode` | `enforce` \| `advisory` | no | Whether the gate blocks (`enforce`) or only reports (`advisory`). The base branch's config wins over the CI setting. On GitLab, where anyone who may run a pipeline can set variables, only this key can make the gate advisory. A child config cannot relax a parent's `enforce`. |
| `tenant` | string | no | The tenant this repository belongs to: the company, or an agency's client, whose people approve its changes. An org preset sets it; a child config cannot change a parent's tenant (a warning, and the parent's stands). The gate stamps it into every gate record, gate event, and change record, and approvals are scoped to it: an identity written `<tenant>:<login>` or `<tenant>:email:<address>` belongs to that tenant, an unqualified one to this tenant, and an approval by an identity of another tenant never counts. |
| `extends` | list of table (`extends`) | no | Parent configs merged first. A child may only tighten gates and cannot lower the profile. |
| `locks` | list of `disable_rules` \| `rule_exclusions` \| `scope_exempt_paths` \| `budget_exclude_paths` \| `standard_changes` \| `tenant` | no | Set by a parent config (an org preset): keys its children may not add to or set. Each list key widens what passes; `tenant` binds the repository to its tenant. Children may add locks, never remove them. |
| `locale` | string | no | BCP 47 tag for ticket titles and PR summaries only; declarative, the verifier does not read it. Tokens stay English. |
| `specs_dir` | string | no | Where Spec files live. Default `specs`. |
| `proposals_dir` | string | no | Where proposals live, one folder each. Default `proposals`. Keep a client's proposals in a repository only people cleared for that client can read. |
| `runbook_max_age_days` | integer | no | Days after a runbook's `last_tested` date before `aidd doctor` warns that it is stale. Default 180. A runbook nobody has run lately is a guess at the moment it is needed. |
| `owners` | table | no | Who owns and approves changes in this repo. |
| `mission` | string | no | The team's enduring purpose, set by humans, such as "small shops get paid on time". It changes rarely; `goal` is the current measurable target under it. `aidd next` shows it first in each Spec's why chain, and the session-start hook briefs the agent with it. A child config may replace it. |
| `goal` | string | no | The team's current measurable goal, set by humans, such as "make onboarding succeed on the first try": the target under `mission`. Agents weigh an open choice against it, `aidd watch` writes it into the draft Specs it opens, and `aidd next` shows it in each Spec's why chain. |
| `agents` | table | no | How the agents work in this repository: which roles may propose work nobody asked for, and when they earn more autonomy. `aidd owners` shows the roles with the humans who decide. |
| `standards` | list of table | no | House standards: the team's own written rules, each a Markdown document in the repository, that agents read before a loop step, beside the standards their roles already apply. `aidd owners` lists them by role; `aidd doctor` checks each path, role, and `enforced_by` name. A child config adds entries; it cannot drop or redefine one a parent names. |
| `targets` | table | no | Delivery targets `aidd metrics --dora` checks the five DORA metrics against, and `aidd metrics` the loop-speed metrics. Set them from your own baseline, or from the latest DORA report's distribution; DORA advises comparing a service with its own past, not with other teams. |
| `tests` | list of table (`test_command`) | no | The repository suite, run on every change. Empty means Characterization: every Spec must bring its own commands. |
| `policy` | table | no | The Policy interface: org rules in any language, run from the base branch without tokens. |
| `observe` | table | no | The Observe interface. |
| `gates` | table | no | Overrides that may only tighten the profile. |
| `risk_rules` | list of table | no | Path rules that raise the required route, add dimensions, and name the specialist pool that reviews. |
| `disable_rules` | list of string | no | Baseline risk rule names to turn off. Protected paths cannot be turned off. |
| `rule_exclusions` | table | no | Extra excluded paths for baseline rules, keyed by rule name, such as { "baseline:auth" = ["web/src/components/auth/**"] }. Protected paths have no exclusions. |
| `protected_paths` | list of string | no | Extra protected paths, added to the built-in set. |
| `scope_exempt_paths` | list of string | no | Paths any change may touch outside its scope, such as CHANGELOG.md. Never a catch-all. |
| `budget_exclude_paths` | list of string | no | Paths not counted in the line budget, such as lockfiles and generated code. Never a catch-all. |
| `standard_changes` | list of table | no | Pre-approved change classes that merge on green tests without a human. |
| `identities` | table | no | How platform accounts map to authors and agents. |
| `evidence` | table | no | Where the CI test run publishes evidence. |
| `emergency` | table | no | Emergency route settings. |
| `guard` | table | no | The edit-time guard (`aidd hook pre-edit`). Advisory, like the rest of the hook: it guides agents; the platform's own deploy protections decide. |
| `hooks` | table | no | The session hooks (`aidd hook session-start`, `aidd hook stop`, `aidd hook pre-compact`). Advisory helpers: they never use the network or a model (inside Orca, `orca_status` only calls the local `orca` CLI), and they allow whenever they cannot tell. |
<!-- aidd:end -->

## Parents, presets, and locks

`extends` layers parent configs under this one, and an org preset (`AIDD_ORG_PRESET`, or `org-preset-url` on the reusable workflow) is the root parent of every repository config. When they merge:

- lists merge, scalars override, and every `[gates]` value keeps the strictest one
- a child cannot choose a weaker profile, or replace its parent's reviewer pools, Policy, evidence source, or identity exemptions
- a parent's `locks` names widening keys (`disable_rules`, `rule_exclusions`, `scope_exempt_paths`, `budget_exclude_paths`, `standard_changes`) that its children cannot add to; an org preset locks `disable_rules`, `rule_exclusions`, and `scope_exempt_paths` without saying so
- a child that replaces its parent's `owners.approvers` gets a warning
- a child cannot relax a parent's `mode = "enforce"`
- a child cannot change a parent's `tenant` (a warning, and the parent's stands); a parent may also lock it with `locks = ["tenant"]`. With a tenant, write an identity of another company as `<tenant>:<login>` or `<tenant>:email:<address>`: its approvals never count here ([METHOD.md §8](METHOD.md#tenants))
- a preset's own parents are fetched by URL only, never from the repository, and a URL parent needs its `sha256`

## `[owners]`

`[owners]`: who may approve, and which specialist pools review high-risk changes. The table marks `approvers` as not required because the schema accepts an empty list, but the gate fails closed on one: every profile, solo included, needs at least one Approver. Local-first, name yourself by the email your commits use, `email:you@example.com`.

<!-- aidd:gen fields:config-owners -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `default_team` | string | no | owner_team that `aidd new` writes into new objects. |
| `approvers` | list of string | no | Eligible Approvers: users, @org/team, or `email:you@example.com` (local-first: the email your commits use). The schema accepts an empty or missing list, but the gate fails closed on it: every profile needs at least one Approver, and until then no change can merge. Under solo, `aidd init` fills in your own login or commit email. |
| `reviewers` | table | no | Specialist reviewer pools by name: `security`, `privacy`, `finance`, `compliance`, `data`, or any pool a risk rule names. A major change needs an approval from each pool its reasons name; an unbound pool falls back to `security`. Locked once a parent sets a pool. |
| `paths` | list of table | no | Per-path owners for monorepos. For every entry whose paths the change touches, at least one approval must come from that entry's approvers. |
| `codeowners` | boolean | no | Also read per-path Approvers from the base branch's CODEOWNERS (last matching rule wins), for Spec approval and Merge approval. Once a parent sets true, it stays true. |
| `backup_approvers` | list of string | no | Who to ask when a wait for an Approver passes `gates.escalate_after_minutes`: `aidd next` names them. Naming them changes nobody's eligibility: a backup approves only when they are an eligible Approver for the change. |
<!-- aidd:end -->

## `[[owners.paths]]`

`[[owners.paths]]`: extra approvers for an area of a monorepo.

<!-- aidd:gen fields:config-owners-paths -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `paths` | list of string | yes | Globs this entry owns. |
| `approvers` | list of string | yes | Users or @org/team; one of them must approve a change that touches these paths. |
<!-- aidd:end -->

## `mission`, `goal`, and `[agents]`

`mission` is the team's enduring purpose, which changes rarely; `goal` is the current measurable target under it, one sentence the humans agree on, the goal every agent weighs an open choice against. Where they show up:

- `aidd next` opens each Spec's why chain with both, followed by its Initiative, Epic, and hypothesis.
- The session-start hook briefs the agent with one `Mission: ... / Goal: ...` line.
- `aidd watch` writes the goal into the draft Specs it opens, so triage weighs a breach against it.
- `aidd doctor` warns when a team has none.

A child config may replace either. Put them with the other top-level keys, before the first table: TOML reads a key written after `[owners]` as part of `[owners]`.

`[agents]`: how the agents work. `proactive_roles` names the roles that may propose work nobody asked for, always as a draft Spec with `proposed_by = "agent:<role>"` that stays a draft until a person records `triage` (accepted, declined, duplicate, or snoozed; `aidd next` asks a person first, and `aidd validate` fails such a Spec past draft without it, [METHOD.md §5.1](METHOD.md#51-status)), and `[agents.autonomy]` sets the evidence `aidd metrics --autonomy` needs before it suggests less review. `aidd owners` shows the roles with the humans who decide ([ADOPTION.md](ADOPTION.md#multiplayer-one-team-humans-and-agents)).

```toml
mission = "small shops get paid on time"
goal = "make onboarding succeed on the first try"

[agents]
proactive_roles = ["product-manager", "sre"]   # default: product-manager, agile-coach, sre; [] means agents only work when asked

[agents.autonomy]
min_changes = 20                               # default 10
```

<!-- aidd:gen fields:config-agents -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `proactive_roles` | list of string | no | Agent roles that may propose work nobody asked for, always as a draft Spec with `proposed_by = "agent:<role>"` that stays a draft until a person records `triage` (`aidd validate` enforces it). Default: product-manager, agile-coach, and sre. An empty list means agents only work when asked. |
| `models` | table | no | The model each aidd-team role runs on, as `provider/model` (`anthropic/claude-opus-5-5`), keyed by tier (`reasoning`, `execution`) or by role name, which wins over its tier. `aidd init --team` and `aidd upgrade` write it into each harness's own agent model field: Claude Code takes only an `anthropic/` model and Codex only an `openai/` one, OpenCode the whole `provider/model`, Kiro and Copilot the model name; where a harness cannot run it, the generated file says so and the harness's default runs. Unset: the tier's default per harness. |
| `independent_review` | boolean | no | Ask for review on another model: `aidd doctor` warns when the reviewer or the verifier resolves, through `models`, to the developer's model family (`anthropic/claude`, `openai/gpt`), or when `models` leaves one of them unset. The reviewer and the verifier start their reports with the harness and the model they ran on. Default false. |
| `autonomy` | table | no | When `aidd metrics --autonomy` suggests more autonomy for an agent and a kind of change. A group with any failed change or reworked Spec stays at the first stage. The report only suggests; a person decides. |
<!-- aidd:end -->

`[agents.autonomy]`: the evidence `aidd metrics --autonomy` needs before it suggests less review for an agent and a kind of change.

<!-- aidd:gen fields:config-agents-autonomy -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `min_changes` | integer | no | Changes needed before the report suggests reviewing only the trade-offs. Default 10. |
| `min_first_pass` | number | no | Share of passed changes that passed on the first try, needed for that stage. Default 0.8. |
| `standard_min_changes` | integer | no | Changes needed before the report names the work a candidate standard change. Default 25. |
| `standard_min_first_pass` | number | no | First-try share needed for a candidate standard change. Default 0.9. |
<!-- aidd:end -->

## `[[standards]]`

`[[standards]]`: house standards, the team's own rules beside the ones each role already applies. Each names a Markdown document and the aidd-team roles that read it before their step, and optionally the paths that make it apply and the `[[tests]]` that enforce it.

- `aidd owners` lists them by role, marked "enforced by <test>" or "guidance", and `aidd owners --json --changed <paths>` gives an agent exactly the ones to load for a change.
- `aidd doctor` warns about a missing document, an unknown role, or an `enforced_by` naming no test.
- A child config adds standards; it cannot drop or redefine one a parent names.

```toml
[[standards]]
name = "api-errors"
path = "docs/standards/api-errors.md"
roles = ["developer", "reviewer"]
when_changed = ["src/api/**"]
enforced_by = ["contract"]            # a [[tests]] entry that checks the rule

[[standards]]
name = "writing"
path = "docs/standards/writing.md"
roles = ["*"]                         # guidance for every role
```

<!-- aidd:gen fields:config-standards -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | Stable name, shown by `aidd owners`, such as `api-errors`. |
| `path` | string | yes | The Markdown document that states the standard, repo-relative, such as `docs/standards/api-errors.md`. |
| `roles` | list of string | yes | aidd-team role keys that read it before their step, such as `developer` or `reviewer`, or `*` for every role. |
| `when_changed` | list of string | no | Load it only for a change that touches one of these paths. Omit to load it for every change. |
| `enforced_by` | list of string | no | Names of `[[tests]]` entries that check the rule, so the gate enforces it. Without one, the standard is guidance a reviewer checks. |
<!-- aidd:end -->

`runbook_max_age_days` (default 180): how old a runbook's `last_tested` may be before `aidd doctor` warns. Runbooks live in `docs/runbooks/` and postmortems in `docs/postmortems/`; `aidd new runbook` and `aidd new postmortem` write them, and `aidd validate` checks them.

## `extends`

Each entry names one parent config.

<!-- aidd:gen fields:config-extends -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `path` | string | no | Repo-relative path to a parent config: no leading / or ./, no .., backslashes, or wildcards. |
| `url` | string | no | HTTPS URL of a parent config. |
| `sha256` | string | no | Required with url. Pins the content. |
<!-- aidd:end -->

## `[targets]`

`[targets]`: the delivery targets `aidd metrics --dora` checks the five DORA software delivery metrics against, and `aidd metrics` the loop-speed metrics (time to first feedback, approval wait, flow efficiency). Either exits 1 when one is missed, so a scheduled job can raise it. Set them from your own baseline first, then tighten; DORA publishes how its survey respondents are distributed on each metric every year, and advises comparing a service with its own past, not with other teams. `cost_per_change` is display only: `aidd metrics --cost` shows whether it is met and never exits 1 for it.

```toml
[targets]
deployments_per_week = 10
lead_time_hours = 24
change_fail_rate = 0.1
recovery_days = 1
rework_rate = 0.05
first_feedback_minutes = 30
approval_wait_p90_minutes = 1440
flow_efficiency_min = 0.4
cost_per_change = 5
```

<!-- aidd:gen fields:config-targets -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `deployments_per_week` | number | no | At least this many changes passing the gate per week. |
| `lead_time_hours` | number | no | At most this many median hours from a change's first gate run to its first pass. |
| `change_fail_rate` | number | no | At most this share of released Specs rolled back or failing observe. |
| `recovery_days` | number | no | At most this many median days to restore a failed release. |
| `rework_rate` | number | no | At most this share of passed changes on the emergency route. |
| `first_feedback_minutes` | number | no | At most this many median minutes from a head's push to the first gate decision holding its test results. `aidd metrics` exits 1 when missed. |
| `approval_wait_p90_minutes` | number | no | At most this many minutes at the 90th percentile of the slowest approval's wait (Spec approval, Merge approval, specialist review). `aidd metrics` exits 1 when missed. |
| `flow_efficiency_min` | number | no | At least this share of lead time (opened to first pass) not spent waiting on a human approval. `aidd metrics` exits 1 when missed. |
| `cost_per_change` | number | no | At most this mean cost per change in `aidd metrics --cost`, in the ledger's one currency. Display only: never a gate rule, never pauses work, never sets the exit code. |
<!-- aidd:end -->

## `[[tests]]`

`[[tests]]`: the repository suite, run on every change beside the Spec's own tests; empty means every Spec brings its own commands (Characterization, [METHOD.md §10](METHOD.md#10-scale-modules)). Each entry is a test command. `new_behavior` belongs to a Spec's tests and is never set here.

<!-- aidd:gen fields:test_command -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | Stable name used in evidence. |
| `command` | list of string | yes | Command vector, one argument per item. Never a shell string. |
| `new_behavior` | boolean | no | True when this command proves new or fixed behavior. It must fail on the base commit (red) and pass on head (green). |
| `timeout_seconds` | integer | no | Wall-clock limit. A timeout is a fail. Default 1800. |
| `when_changed` | list of string | no | Run and require this command only when a changed path matches. Omit to run it on every change. |
| `covers` | list of string | no | In a Spec: the Acceptance items this command proves, by id (`A1`, `A2`, ...). Optional; once any command declares it, `aidd validate` warns about an Acceptance item no command covers, and about an id the Acceptance section does not have. The gate never reads it. |
<!-- aidd:end -->

## `[policy]`

`[policy]`: your own command the gate runs for freezes and deny lists.

<!-- aidd:gen fields:config-policy -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `command` | list of string | no | Prints allow, deny, or freeze, or a JSON answer with findings. No output or a timeout is deny. Locked once a parent sets it. |
<!-- aidd:end -->

## `[observe]`

`[observe]`: the post-release health check.

<!-- aidd:gen fields:config-observe -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `command` | list of string | no | Default post-release check when a Spec's observe block names none. |
| `bands` | list of table | no | Control bands for `aidd watch`: a metric judged against its recent baseline. Detection is deterministic; the tier sets what an agent may do (log, diagnose read-only, propose a change through the gate). |
<!-- aidd:end -->

## `[gates]`

Each value may only tighten the profile. Two keys are queue limits for people, which only `aidd next` reads and the gate never does: `max_open_per_approver` (the most open approval waits one Approver should hold; 3 under team, org, and regulated, off under solo) and `escalate_after_minutes` (after which `aidd next` marks a wait and names `owners.backup_approvers`; off by default). For both, 0 is off and a lower number tightens.

<!-- aidd:gen fields:config-gates -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `separation_of_duties` | boolean | no | Approvers must differ from the change's authors. Only true tightens. |
| `spec_approval_routes` | list of `route` | no | Routes that need Spec approval, by hash, before implementation. |
| `specialist_spec_approval` | boolean | no | Each required specialist pool also approves the Spec hash on major. |
| `approvals` | table (`route_ints`) | no | Approvals needed at Merge approval, per route. |
| `specialist_approvals` | integer | no | Approvals needed from each required specialist pool on major, and on emergency changes that touch protected paths. |
| `cooloff_minutes` | table (`route_ints`) | no | Minutes after the platform first saw the head commit (its earliest check suite on the pull request's branch; the pipeline's creation on GitLab; locally, the head commit's committer date, which the committer sets) before an approval counts, per route. |
| `policy_required_routes` | list of `route` | no | Routes that fail without a bound Policy command. |
| `provenance` | `declare` \| `every_commit` | no | declare: assisted_by lists every agent a commit names (an `Assisted-by:` trailer, or a `Co-authored-by:` agent). every_commit: also, every non-merge commit carries an `Assisted-by:` trailer (`Assisted-by: none` when no agent wrote it). |
| `red_green` | `warn` \| `require` | no | warn or require that new-behavior tests fail on base. |
| `standard_changes` | boolean | no | Allow configured standard changes. Only false tightens. |
| `observe_required_routes` | list of `route` | no | Routes whose Spec must have an observe block. |
| `max_changed_lines` | table (`budget_ints`) | no | Maximum changed lines per route, after budget_exclude_paths and the files Spec approval froze. The standard and emergency routes have no budget. |
| `unlinked_authors` | `warn` \| `fail` | no | A commit author the platform cannot map to an account might be an Approver: warn, or fail. Only fail tightens. |
| `spec_approval_proof` | `optional` \| `require` | no | optional: an approval line may name the commit it was given on, and the gate records whether Spec approval came before implementation. require: only such approvals count, on a commit that changed nothing but the Spec and its frozen files. Only require tightens. |
| `local_approvals` | `any` \| `signed` | no | Local-first approvals (`aidd approve`, read by the local gate and `aidd ship`): any counts every recorded approval; signed counts only those whose git signature verifies as good (with SSH signing, from the approver's own email principal). Read from the base branch, so an agent cannot switch it off. Only signed tightens. |
| `max_open_per_approver` | integer | no | The most open waits (Spec approval or Merge approval) one Approver should hold; 0 turns it off. `aidd next --waiting-on-me` and `aidd next --all` warn when an Approver holds more. A queue signal only: the gate never reads it. A lower number (not 0) tightens. |
| `escalate_after_minutes` | integer | no | Minutes a Spec may wait for an Approver before `aidd next` marks the wait escalated and names `owners.backup_approvers`; 0 turns it off. It never approves anything and never changes the gate's decision. A lower number (not 0) tightens. |
<!-- aidd:end -->

## `[[risk_rules]]`

`[[risk_rules]]`: paths that raise the route or name a reviewer pool.

<!-- aidd:gen fields:config-risk_rules -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | Rule name, shown in findings and usable in rule_exclusions and disable_rules. |
| `paths` | list of string | yes | Globs that trigger the rule. |
| `route` | `minor` \| `normal` \| `major` | no | Minimum route when the rule matches; without it, only the dimensions raise the route. |
| `dimensions` | list of `dimension` | no | Risk dimensions the change must declare when the rule matches. |
| `reviewers` | list of string | no | Specialist pools that must approve when the rule makes the change major. Default: the pools its dimensions name, else `security`. |
| `exclude` | list of string | no | Paths this rule never matches. |
<!-- aidd:end -->

## `[[standard_changes]]`

`[[standard_changes]]`: bot changes that merge on green tests with no human.

<!-- aidd:gen fields:config-standard_changes -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | Class name, recorded as standard_change. |
| `paths` | list of string | yes | Globs the change may touch; any other path takes it off the standard route. |
| `authors` | list of string | yes | Every commit author and the change author must be listed, usually bots. |
| `max_changed_lines` | integer | no | Maximum changed lines for the class. |
| `type` | `type` | no | Type recorded when a bot PR has no block. Default deps. |
| `dimensions` | list of `dimension` | no | Risk dimensions recorded when a bot PR has no block. Default ["third_party"]. |
<!-- aidd:end -->

## `[identities]`

`[identities]`: bot and system accounts, which can never approve.

<!-- aidd:gen fields:config-identities -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `system_accounts` | list of string | no | Platform bookkeeping accounts that are never authors, such as web-flow. Only bot-like accounts (`*[bot]`, web-flow, github-actions) are accepted. |
| `bots` | list of string | no | Agent accounts that act as implementers. They can never approve, and their commits count as agent-written for provenance. |
<!-- aidd:end -->

## `[evidence]`

`[evidence]`: where the gate finds test results.

<!-- aidd:gen fields:config-evidence -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `workflow` | string | no | CI workflow name that uploads evidence. Default aidd-tests. |
| `artifact` | string | no | Artifact name. Default aidd-evidence. |
| `workflow_path` | string | no | Workflow file whose runs carry the evidence artifact. Default .github/workflows/aidd-tests.yml. Point it at your existing CI to avoid running the suite twice. |
| `status_checks` | list of string | no | Check runs from your existing CI that must succeed on head (success, neutral, or skipped), as evidence beside or instead of [[tests]]. GitHub only. Only check runs count, from an app in status_check_apps and the pull request's own branch; commit statuses never count. Lists from parents merge. |
| `status_check_apps` | list of string | no | GitHub App slugs whose check runs count for status_checks. Default ["github-actions"]. Locked once a parent sets it. |
| `signer_workflow` | string | no | owner/repo/.github/workflows/file.yml of a central test workflow (an organization required workflow). When set, the gate accepts evidence only with a valid GitHub artifact attestation signed by that workflow. Locked once a parent sets it. |
<!-- aidd:end -->

## `[emergency]`

`[emergency]`: deadlines for the review that follows a production repair.

<!-- aidd:gen fields:config-emergency -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `review_sla_days` | integer | no | Longest allowed gap between the day an emergency change opens and its review_due. Default 2. A child takes the smaller value. |
<!-- aidd:end -->

## `[guard]`

`[guard]`: commands the edit-time hook holds for a person, such as a production deploy.

<!-- aidd:gen fields:config-guard -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `gated_commands` | list of table | no | Shell commands the edit-time hook denies to every agent until a person approves them, such as a production deploy. Default none. A child config adds gates to its parents'; it cannot drop or redefine one a parent names. |
<!-- aidd:end -->

### `[[guard.gated_commands]]`

`[[guard.gated_commands]]`: shell commands that wait for a person, such as a production deploy. The default config writes none. That is how autonomy is tiered per environment: agents run the build and staging freely, and a person allows production.

- **What is held.** The edit-time hook (`aidd hook pre-edit`, which the Claude Code plugin and `aidd init --agent-hooks` wire) denies a matching Bash command to every agent, the session, a role, or a helper.
- **Until when.** Until the variable named in `requires` holds a non-empty value in the environment Claude Code started with. A person sets it when they allow the deploy.
- **Why an agent cannot.** The hook reads the environment Claude Code gave it, not the agent's shell, and a command that names the variable itself is denied.

```toml
[[guard.gated_commands]]
name = "production deploy"
match = ["deploy", "production"]       # all must match one simple command, ignoring case
environment = "production"
requires = "RELEASE_APPROVAL"          # the approver starts the session with RELEASE_APPROVAL=CHG-1234 claude
message = "Production deploys need a change ticket from #release."

[[guard.gated_commands]]
name = "terraform apply"
match = ["terraform apply*"]           # a glob; no `requires`, so agents never run it
```

The hook matches each simple command of the line (it follows `&&`, `;`, `|`, `cd`, and `sh -c`), so `echo deploy; ls production` does not match, and `cd infra && make deploy ENV=production` does. It is best-effort parsing and advisory, like the rest of the hook: a deploy started from a script whose name matches nothing, or through an interpreter, is not seen. Keep the platform's own protection (a GitHub environment with required reviewers, a GitLab protected environment) as the control, and use this to stop the agent before it asks the platform.

<!-- aidd:gen fields:config-guard-gated_commands -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | Gate name, shown in the deny message. |
| `match` | list of string | yes | Patterns that must all match one simple command, ignoring case: a pattern with `*`, `?`, or `[` is a glob over the whole command, any other a substring. ["deploy", "production"] matches `make deploy ENV=production`. |
| `environment` | string | no | Label of the environment the command reaches, such as production or staging, shown in the deny message. |
| `requires` | string | no | Environment variable a person sets to a non-empty value, in the environment Claude Code starts with, to approve the command, such as RELEASE_APPROVAL. A command that names the variable itself is denied. Without it, agents never run the command. |
| `message` | string | no | Extra text for the deny message, such as where to ask for approval. |
<!-- aidd:end -->

## `[hooks]`

`[hooks]`: the Claude Code session hooks, which the aidd plugin and `aidd init --agent-hooks` wire beside the edit-time guard. They are advisory helpers: deterministic, no model, no network, and they allow whenever they cannot tell or fail.

- `aidd hook session-start` (SessionStart): adds a summary of `aidd next`, at most 15 lines, to the agent's context. After a compaction (standard and above) it adds a reminder to write the handoff note (Done, Next, Needs, Stopped at) into the Spec or the PR/MR.
- `aidd hook stop` (Stop, and SubagentStop for an aidd-team role that writes code): when an active Spec has changes in its Tasks' scope and no evidence file (`aidd-evidence/evidence.json`, or the `[evidence] artifact` folder) records every applicable `[[tests]]` command and the Spec's `tests.commands` as passed on HEAD, it tells the agent to run `aidd test` and report the result. At standard the agent gets the reminder once; at strict the stop is blocked once with that reason. It never continues an agent a stop hook already continued.
- Inside [Orca](ORCA.md#the-workspace-card), session-start and stop also write the first step of `aidd next` on the worktree's Orca card, through the `orca` CLI. Display only, never evidence; it gives up after 2 seconds and does nothing outside Orca. `orca_status = false` turns it off.
- `aidd hook pre-compact`: a no-op. Claude Code's PreCompact output can only block a compaction, not add context, so the handoff reminder comes after the compaction, from session-start.

```toml
[hooks]
level = "strict"        # default: solo minimal, team and org standard, regulated strict
compact_note = false    # each hook turns off on its own: session_start, stop_check, compact_note
```

A child config cannot lower its parent's level, or the level its parent's profile starts at, and cannot turn off a hook its parent turns on. The edit-time guard logs each deny to `.aidd/work/guard.jsonl`, which git ignores; `aidd metrics --guard` counts them by reason and by role.

<!-- aidd:gen fields:config-hooks -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `level` | `minimal` \| `standard` \| `strict` | no | How much the session hooks do. minimal: `aidd hook session-start` adds a summary of `aidd next`. standard: also the stop reminder (`aidd hook stop` asks the agent once to run `aidd test` when in-scope changes have no passing evidence on HEAD) and, after a compaction, the handoff note reminder. strict: the stop reminder blocks the stop instead. Default by profile: solo minimal, team and org standard, regulated strict. A child config cannot lower a parent's level. |
| `session_start` | boolean | no | Run `aidd hook session-start`. Default true. A child config cannot turn off a hook a parent config turns on. |
| `stop_check` | boolean | no | Run `aidd hook stop` for Stop and SubagentStop. Default true. A child config cannot turn off a hook a parent config turns on. |
| `compact_note` | boolean | no | Remind the agent of the handoff note (an ```aidd-handoff block: done, next, needs, stopped_at) after a compaction. Default true. A child config cannot turn off a hook a parent config turns on. |
| `orca_status` | boolean | no | Inside Orca, with its `orca` CLI on PATH, put the first step of `aidd next` on the worktree's Orca card (its comment) when session-start and stop run. Display only, never evidence or an approval; time-boxed to 2 seconds and silent on failure. Does nothing outside Orca. Default true. |
<!-- aidd:end -->
