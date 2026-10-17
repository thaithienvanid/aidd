# Config fields

Read this file to maintain `.aidd/config.yaml` or to read evidence. Agents rarely need it. `aidd gen-docs` generates the tables from the schemas that ship with the CLI.

**Contents**

<!-- aidd:gen toc -->
- [Config (`.aidd/config.yaml`)](#config-aiddconfigyaml)
- [Project constraints (`project`)](#project-constraints-project)
- [Evidence (`.aidd/evidence/evidence.json`)](#evidence-aiddevidenceevidencejson)
<!-- aidd:end -->

## Config (`.aidd/config.yaml`)

<!-- aidd:gen fields:config -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `aidd_version` | string | yes | The aidd release this record conforms to; the method and the toolkit share one version. |
| `profile` | `profile` | yes | Conformance profile. Each one is stricter than the one before. |
| `mode` | `enforce` \| `advisory` | no | Whether the gate blocks (`enforce`) or only reports (`advisory`). The base branch's config wins over the CI setting. On GitLab, where anyone who may run a pipeline can set variables, only this key can make the gate advisory. A child config cannot relax a parent's `enforce`. |
| `components` | mapping | no | The parts of aidd that run in this repository. Each is on unless set to false, and each turns off alone: a part that is off says nothing, and the others keep working. The gate is set by `mode`, and the team by installing the aidd-team plugin. A child config cannot turn off a part its parent turns on. |
| `tenant` | string | no | The tenant this repository belongs to: the company, or an agency's client, that approves its changes. An org preset sets it; a child config cannot change a parent's tenant (a warning, and the parent's stands). The gate stamps it into every gate record, gate event, and change record, and approvals are scoped to it: an identity written `<tenant>:<login>` or `<tenant>:email:<address>` belongs to that tenant, an unqualified one to this tenant, and an approval by an identity of another tenant never counts. |
| `extends` | list of mapping (`extends`) | no | Parent configs merged first. A child may only tighten gates and cannot lower the profile. |
| `locks` | list of `disable_rules` \| `rule_exclusions` \| `scope_exempt_paths` \| `budget_exclude_paths` \| `standard_changes` \| `tenant` \| `project` | no | Set by a parent config (an org preset): keys its children may not add to or set. Each list key widens what passes; `tenant` binds the repository to its tenant; `project` binds the parent's `project`, which a child may then add to and tighten, never loosen. Children may add locks, never remove them. |
| `locale` | string | no | Agent-facing only: the BCP 47 tag an agent writes ticket titles and PR summaries in. aidd itself reads it nowhere, and the gate never does. Tokens stay English. |
| `specs_dir` | string | no | Where Spec files live. Default `specs`. A folder inside the repository, never its top: the Specs folder is a role's write area. |
| `proposals_dir` | string | no | Where proposals live, one folder each. Default `proposals`. A folder inside the repository, never its top: a change only to it needs no Spec. Keep a client's proposals in a repository only people cleared for that client can read. |
| `docs` | mapping | no | Linked documents: where `aidd new` writes them, and which ones `aidd validate` asks for. |
| `runbook_max_age_days` | integer | no | Days after a runbook's `tested_on` date before `aidd doctor` warns that it is stale. Default 180. A runbook nobody has run lately is a guess at the moment it is needed. |
| `owners` | mapping | no | Who owns and approves changes in this repo. |
| `mission` | string | no | The team's enduring purpose, set by humans, such as "small shops get paid on time". It changes rarely; `goal` is the current measurable target under it. `aidd list` shows it first in each Spec's why chain, and the session-start hook briefs the agent with it. A child config may replace it. |
| `goal` | string | no | The team's current measurable goal, set by humans, such as "make onboarding succeed on the first try": the target under `mission`. Agents weigh an open choice against it, `aidd observe --band` writes it into the draft Specs it opens, and `aidd list` shows it in each Spec's why chain. |
| `agents` | mapping | no | How the agents work in this repository: which roles may suggest work nobody asked for, and when they earn more autonomy. `aidd owners` shows the roles with the humans who decide. |
| `standards` | list of mapping | no | Standards: the team's own written rules and its copies of aidd's library standards (`aidd standard add`), each a Markdown document in the repository that agents read before a loop step, beside the standards their roles already apply. Each is opinionated (the default) or industry. `aidd owners` lists them by role with their type; `aidd doctor` checks each path, role, and `enforced_by` name, and each copy against the library. A child config adds entries; it cannot drop or redefine one a parent names. |
| `standards_policy` | mapping | no | A company's rules for library standards, usually in its org preset: `aidd standard add` and `aidd stack add` follow them and `aidd doctor` reports a breach. Only opinionated ids: an industry standard is never excluded or replaced, only waived per project, with a reason and an expiry. A child config adds and tightens: it cannot drop a parent's entry, require what a parent excludes, or allow a stack the parent does not. |
| `targets` | mapping | no | Delivery targets `aidd metrics --dora` checks the five DORA metrics against, and `aidd metrics` the loop-speed metrics. Set them from your own baseline, or from the latest DORA report's distribution; DORA advises comparing a service with its own past, not with other teams. |
| `tests` | list of mapping (`test_command`) | no | The repository suite, run on every change. Empty means Characterization: every Spec must bring its own commands. |
| `policy` | mapping | no | The Policy interface: org rules in any language, run from the base branch without credentials unless `pass_env` names them. |
| `observe` | mapping | no | The Observe interface. |
| `preview` | mapping | no | The one-command local preview: no hosting, no cost. The verifier starts it from a clean checkout of the head and records screenshots, a trace or video, and API transcripts under `.aidd/evidence/preview/<head_sha>/`, for people; the gate never reads it. `aidd init` fills it only when the command is obvious (a Docker Compose file). |
| `gates` | mapping | no | Overrides that may only tighten the profile. |
| `risk_rules` | list of mapping | no | Path, dependency, and content rules that raise the required route, add dimensions, and name the specialist pool that reviews. |
| `disable_rules` | list of string | no | Baseline risk rule names to turn off, such as `baseline:payments` in a repository with no payment code. Protected paths cannot be turned off; to keep a rule and drop one folder from it, use `rule_exclusions`. |
| `rule_exclusions` | mapping | no | Extra excluded paths for baseline rules, keyed by rule name. The recipe for a folder a rule matches by name that holds no such logic, such as UI components: `rule_exclusions: {"baseline:auth": ["src/components/permissions/**"]}` keeps permission badges out of the auth rule while src/auth/ stays major. Narrow a rule this way rather than disabling it. Protected paths have no exclusions. |
| `protected_paths` | list of string | no | Extra protected paths, added to the built-in set. |
| `scope_exempt_paths` | list of string | no | Paths any change may touch outside its scope, such as CHANGELOG.md. Never a catch-all. |
| `budget_exclude_paths` | list of string | no | Paths not counted in the line budget, such as lockfiles and generated code. Never a catch-all. |
| `standard_changes` | list of mapping | no | Pre-approved change classes that merge on green tests without a human. |
| `identities` | mapping | no | How platform accounts map to authors and agents. |
| `evidence` | mapping | no | Where the CI test run publishes evidence. |
| `emergency` | mapping | no | Emergency route settings. |
| `guard` | mapping | no | The guard (`aidd hook pre-tool`). Advisory, like the rest of the hook: it guides agents; the platform's own deploy protections decide. |
| `hooks` | mapping | no | The session hooks (`aidd hook session-start`, `aidd hook prompt-submit`, `aidd hook stop`, `aidd hook pre-compact`). Advisory helpers: they never use the network or a model (inside Orca, `orca_status` only calls the local `orca` CLI), and they allow whenever they cannot tell. |
| `autopilot` | mapping | no | Autopilot runs the AIDD loop between your decisions: aidd decides each next step and stops whenever a person must decide. These are its limits, which `aidd autopilot next` reads. Each has a default or is off, so nothing asks a question. |
| `project` | mapping | no | The project's constraints and rules, set by humans: a technology radar, the hosting, a budget, the team's own rules each with its why, and the waivers a person approved. Agents read them in Specify and Review; `aidd gate --paths` and `aidd owners` print the rules that apply to the paths in question, must first. `aidd validate` checks them; the gate never reads them. A parent that lists `project` in `locks` binds its rules, its hold list, its budget, and its hosting: a child may add rules and raise a rule's level, never lower one, waive a locked rule, or spend more. |
<!-- aidd:end -->

### Config sub-tables

#### `owners`

<!-- aidd:gen fields:config-owners -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `default_team` | string | no | owner_team that `aidd new` writes into new objects. |
| `approvers` | list of string | no | Eligible Approvers: users, @org/team, or `email:you@example.com` (local-first: the email your commits use). The schema accepts an empty or missing list, but the gate fails closed on it: every profile needs at least one Approver, and until then no change can merge. Under solo, `aidd init` fills in your own login or commit email. |
| `specialists` | mapping | no | Specialist Approver pools by name: `security`, `privacy`, `finance`, `compliance`, `data`, or any pool a risk rule names. A major change needs an approval from each pool its reasons name; an unbound pool falls back to `security`, so a financial major change (`baseline:payments`) goes to `finance` when it is bound and to `security` until then. Locked once a parent sets a pool. |
| `paths` | list of mapping | no | Per-path owners for monorepos. For every entry whose paths the change touches, at least one approval must come from that entry's approvers. |
| `codeowners` | boolean | no | Also read per-path Approvers from the base branch's CODEOWNERS (last matching rule wins), for Spec approval and Merge approval. Once a parent sets true, it stays true. |
| `backup_approvers` | list of string | no | Who to ask when a wait for an Approver passes `gates.escalate_after_minutes`: `aidd list` names them. Naming them changes nobody's eligibility: a backup approves only when they are an eligible Approver for the change. |
<!-- aidd:end -->

#### `owners.paths`

<!-- aidd:gen fields:config-owners-paths -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `paths` | list of string | yes | Globs this entry owns. |
| `approvers` | list of string | yes | Users or @org/team; one of them must approve a change that touches these paths. |
<!-- aidd:end -->

`tests` entries use the test command fields in `references/spec.md`. `extends` entries:

<!-- aidd:gen fields:config-extends -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `path` | string | no | Repo-relative path to a parent config: no leading / or ./, no .., backslashes, or wildcards. |
| `url` | string | no | HTTPS URL of a parent config. |
| `sha256` | string | no | Required with url. Pins the content. |
<!-- aidd:end -->

#### `policy`

<!-- aidd:gen fields:config-policy -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `command` | list of string | no | Prints allow, deny, or freeze, or a JSON answer with findings. No output or a timeout is deny. Locked once a parent sets it. |
| `pass_env` | list of string | no | Credential-like variables (names with TOKEN, SECRET, PASSWORD, KEY, or CREDENTIAL) the Policy command may see, by name; every other one is dropped from its environment, as for the test commands. Locked once a parent sets it. |
<!-- aidd:end -->

#### `gates`

Each value may only tighten the profile.

<!-- aidd:gen fields:config-gates -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `separation_of_duties` | boolean | no | Approvers must differ from the change's authors. Only true tightens. |
| `spec_approval_routes` | list of `route` | no | Routes that need Spec approval, by hash, before implementation. |
| `specialist_spec_approval` | boolean | no | Each required specialist pool also approves the Spec hash on major. |
| `approvals` | mapping (`route_ints`) | no | Approvals needed at Merge approval, per route. |
| `specialist_approvals` | integer | no | Approvals needed from each required specialist pool on major, and on emergency changes that touch protected paths. |
| `cooloff_minutes` | mapping (`route_ints`) | no | Minutes after the platform first saw the head commit (its earliest check suite on the pull request's branch; the pipeline's creation on GitLab; locally, the head commit's committer date, which the committer sets) before an approval counts, per route. |
| `policy_required_routes` | list of `route` | no | Routes that fail without a bound Policy command. |
| `provenance` | `declare` \| `every_commit` | no | declare: assisted_by lists every agent a commit names (an `Assisted-by:` trailer, or a `Co-authored-by:` agent). every_commit: also, every non-merge commit carries an `Assisted-by:` trailer (`Assisted-by: none` when no agent wrote it). |
| `red_green` | `warn` \| `require` | no | warn or require that new-behavior tests fail on base. |
| `standard_changes` | boolean | no | Allow configured standard changes. Only false tightens. |
| `observe_required_routes` | list of `route` | no | Routes whose Spec must have an observe block. |
| `max_changed_lines` | mapping (`budget_ints`) | no | Maximum changed lines per route, after budget_exclude_paths and the files Spec approval froze. The standard and emergency routes have no budget. |
| `unlinked_authors` | `warn` \| `fail` | no | A commit author the platform cannot map to an account might be an Approver: warn, or fail. Only fail tightens. |
| `spec_approval_proof` | `optional` \| `require` | no | optional: an approval line may name the commit it was given on, and the gate records whether Spec approval came before implementation. require: only such approvals count, on a commit that changed nothing but the Spec and its frozen files. Only require tightens. |
| `approval_carry` | `trivial_rebase` \| `none` | no | Whether a Merge approval of an earlier head counts for the new head after a trivial rebase (Gerrit's TRIVIAL_REBASE): the change's diff is identical, byte for byte apart from line offsets, onto a base that descends from the approved one on the protected branch; nobody new committed; no protected path changes; the tests run again on the new head as usual. none: every new head needs a new approval. The emergency route never carries. Only none tightens. |
| `approval_carry_routes` | list of `route` | no | The routes on which `approval_carry` applies; emergency never does. A shorter list tightens. |
| `local_approvals` | `any` \| `signed` | no | Local-first approvals (`aidd approve`, read by the local gate and `aidd ship`): any counts every recorded approval; signed counts only those whose git signature verifies as good (with SSH signing, from the Approver's own email principal). Read from the base branch, so an agent cannot switch it off. Only signed tightens. |
| `local_signers` | string | no | The repository file listing whose SSH signatures count as local approvals, in git's allowed signers format (one `<email> <public key>` line per Approver), read from the base branch's tip and never from the working tree or this machine's git config (default `.aidd/allowed_signers`). The check pins its own settings (SSH signatures, ssh-keygen, this file), so an agent's edit to the machine's gpg config changes nothing. Under `local_approvals: signed` with no such file on the base branch, no local approval counts. A parent config's path stands. |
| `max_open_per_approver` | integer | no | The most open waits (Spec approval or Merge approval) one Approver should hold; 0 turns it off. `aidd list --waiting-on-me` and `aidd list` warn when an Approver holds more. A queue signal only: the gate never reads it. A lower number (not 0) tightens. |
| `max_in_progress_per_owner` | integer | no | The work-in-progress limit: the most Specs in progress one `owner` should hold; unset or 0 is off. `aidd list` warns when a person holds more. A queue signal only: the gate never reads it. A lower number (not 0) tightens. |
| `max_in_progress_days` | integer | no | Work item age: the most days a Spec should stay in progress before `aidd list` flags it as aging (`aged`). Unset is 10; 0 turns the flag off, and the age still shows. Set it from your own cycle time, such as its 85th percentile. A queue signal only: the gate never reads it. A lower number (not 0) tightens. |
| `max_branch_days` | integer | no | Branch age, for trunk-based work: the most days a branch with work the default branch lacks should live before `aidd list` and `aidd doctor` warn, counted from its oldest own commit. Unset is 2 (DORA: hours, merged at least daily; an agent's branch also waits on a person's approvals); 0 turns the warning off. Land the work, behind a flag when it is unfinished, or split it. A queue signal only: the gate never reads it. A lower number (not 0) tightens. |
| `max_open_branches` | integer | no | Open branches, for trunk-based work: the most local branches with work the default branch lacks (goal branches aside; a branch whose work another open branch holds, such as a Task branch merged into its Spec's, counts as that branch) before `aidd list` and `aidd doctor` warn. Unset is 3, DORA's mark; 0 turns the warning off. A queue signal only: the gate never reads it. A lower number (not 0) tightens. |
| `max_goal_days` | integer | no | Goal age: the most days a goal branch (`goal/<name>`) should live before `aidd list` and `aidd doctor` warn, counted from its oldest commit the default branch lacks. Unset is 7; 0 turns the warning off. A long integration branch drifts from the default branch: release what is integrated, or split the goal. A queue signal only: the gate never reads it. A lower number (not 0) tightens. |
| `escalate_after_minutes` | integer | no | Minutes a Spec may wait for an Approver before `aidd list` marks the wait escalated and names `owners.backup_approvers`; 0 turns it off. It never approves anything and never changes the gate's decision. A lower number (not 0) tightens. |
<!-- aidd:end -->

#### `risk_rules`

<!-- aidd:gen fields:config-risk_rules -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | Rule name, shown in findings and usable in rule_exclusions and disable_rules. |
| `paths` | list of string | no | Globs that trigger the rule. A rule names `paths`, `dependencies`, `content`, or a mix. With `content`, the paths only narrow where its patterns are read: a path alone never triggers it. |
| `content` | list of string | no | Regular expressions (Python `re`, searched in each line) that trigger the rule when a line the diff adds matches one, in a file its `paths` match (any file without `paths`) and its `exclude` does not. What the code does, wherever it sits: a raw SQL string, a call to a model API, a new outbound host. The adapter reads the diff with git and sends the matches in the context (`content_matches`); `aidd gate --paths` cannot see content, so a plan's forecast never shows them. A pattern that does not compile is a config error. |
| `dependencies` | list of string | no | Dependency names that also trigger the rule when the diff adds one to a manifest (package.json, requirements*.txt, pyproject.toml, Pipfile, go.mod, Cargo.toml, pom.xml, build.gradle(.kts), *.csproj, Gemfile, composer.json, pubspec.yaml, mix.exs, or a Django settings module's INSTALLED_APPS), wherever the code that uses it sits. A name matches ignoring case and treating `-`, `_`, and `.` alike; one ending in `/` matches every name it starts (an npm scope or a Go module path). A version change never matches, and `exclude` applies to the manifest's path. |
| `route` | `minor` \| `normal` \| `major` | no | Minimum route when the rule matches; without it, only the dimensions raise the route. |
| `dimensions` | list of `dimension` | no | Risk dimensions the change must declare when the rule matches. |
| `specialists` | list of string | no | Specialist Approver pools that must approve the head. A rule below major asks them whenever it matches, on every route (an emergency too, unless it is an exact revert): a pool asked for what the change does, not only for its size. A rule that forces major asks them through the major route. Default: the pools its dimensions name, else `security`, and only when the rule makes the change major. |
| `exclude` | list of string | no | Paths this rule never matches. |
<!-- aidd:end -->

#### `standard_changes`

<!-- aidd:gen fields:config-standard_changes -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | Class name, recorded as standard_change. |
| `paths` | list of string | yes | Globs the change may touch; any other path takes it off the standard route. |
| `authors` | list of string | yes | Every commit author and the change author must be listed, usually bots. |
| `max_changed_lines` | integer | no | Maximum changed lines for the class. |
| `type` | `type` | no | Type recorded when a bot PR has no block. Default deps. |
| `dimensions` | list of `dimension` | no | Risk dimensions recorded when a bot PR has no block. Default ["third_party"]. |
| `update_types` | list of `patch` \| `minor` \| `major` | no | The dependency updates the class takes: patch, minor, major. Read from the diff's manifests and lockfiles (npm, pip, uv, poetry, Go, Cargo) and from Dependabot's `updated-dependencies` metadata, the worst of both; an update it cannot classify counts as major. Default ["patch", "minor"] for a class with the third_party dimension; no limit otherwise. `aidd doctor` warns when a third_party class allows major. |
<!-- aidd:end -->

#### `identities`

<!-- aidd:gen fields:config-identities -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `system_accounts` | list of string | no | Platform bookkeeping accounts that are never authors, such as web-flow. Only bot-like accounts (`*[bot]`, web-flow, github-actions) are accepted. |
| `bots` | list of string | no | Agent accounts that act as implementers. They can never approve, and their commits count as agent-written for provenance. |
<!-- aidd:end -->

#### `evidence`

<!-- aidd:gen fields:config-evidence -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `workflow` | string | no | CI workflow name that uploads evidence. Default aidd-tests. |
| `artifact` | string | no | The name of the CI artifact that carries the evidence. Default aidd-evidence. Locally, `aidd test` writes it to `.aidd/evidence/`; when this is set, the hooks and the status also read a folder of this name. |
| `workflow_path` | string | no | Workflow file whose runs carry the evidence artifact. Default .github/workflows/aidd-tests.yml. Point it at your existing CI to avoid running the suite twice. |
| `status_checks` | list of string | no | Check runs from your existing CI that must succeed on head (success, neutral, or skipped), as evidence beside or instead of `tests`. GitHub only. Only check runs count, from an app in status_check_apps and the pull request's own branch; commit statuses never count. Lists from parents merge. |
| `status_check_apps` | list of string | no | GitHub App slugs whose check runs count for status_checks. Default ["github-actions"]. Locked once a parent sets it. |
| `signer_workflow` | string | no | owner/repo/.github/workflows/file.yml of a central test workflow (an organization required workflow). When set, the gate accepts evidence only with a valid GitHub artifact attestation signed by that workflow. Locked once a parent sets it. |
<!-- aidd:end -->

#### `emergency`

<!-- aidd:gen fields:config-emergency -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `review_sla_days` | integer | no | Longest allowed gap between the day an emergency change opens and its review_due. Default 2. A child takes the smaller value. |
<!-- aidd:end -->

#### `preview`

The one command that starts the app on this machine with seed data. The verifier runs it from a clean checkout of the head (a git worktree) and exercises each Acceptance item. It saves screenshots, a trace or video, and API transcripts under `.aidd/evidence/preview/<head-sha>/`. Then `aidd record preview <head-sha>` writes that folder's `artifacts.json`, which lists them with their SHA-256. For people: the gate decides on exit codes only.

<!-- aidd:gen fields:config-preview -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `command` | list of string | yes | Starts the app on this machine with its seed data (the command loads them), from a clean checkout, such as ["docker", "compose", "up", "--build"]. The verifier runs it in a worktree of the exact head commit. |
| `url` | string | no | Where the running preview answers, such as http://localhost:3000: the address the verifier drives. |
<!-- aidd:end -->

#### `guard.held_commands`

Commands the guard hook denies to every agent until a person approves. `aidd init` writes an entry, named `init: ...`, for each deploy command it finds. These are deploy scripts, Makefile deploy targets, and infrastructure tool commands such as `terraform apply`. A person may delete an entry. Never delete or edit one yourself. To approve one per session, a person adds `requires: VAR`. That person then starts the agent with VAR set to a non-empty value.

**Production flag flips.** A production flag flip is a person's release decision, like a deploy. Hold the command that flips it, or make a production flag file a `protected_paths` entry. Never run that command yourself.

```yaml
guard:
  held_commands:
    - name: production flag flip
      match: [flag, production]  # such as `./scripts/flags set checkout-v2 on --env production`
      requires: FLAG_APPROVAL  # the person who approves starts the session with FLAG_APPROVAL set
```

#### `standards`

Standards are the team's own rules and its copies of library standards. Before a step, read each one listed for your role whose `when_changed` matches the change (`aidd owners --json --changed <paths>`). Never edit a copy (an entry with `vendored`).

<!-- aidd:gen fields:config-standards -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | Stable name, shown by `aidd owners`, such as `api-errors`. |
| `path` | string | yes | The Markdown document that states the standard, repo-relative, such as `docs/standards/api-errors.md`. |
| `roles` | list of string | yes | aidd-team role keys that read it before their step, such as `developer` or `reviewer`, or `*` for every role. |
| `when_changed` | list of string | no | Load it only for a change that touches one of these paths. Omit to load it for every change. |
| `enforced_by` | list of string | no | Names of `tests` entries that check the rule, so the gate enforces it. Without one, the standard is guidance a reviewer checks. |
| `type` | `"opinionated"` | no | `opinionated`, the default and the only value here: a choice the team or company commits to, which a company can require, exclude, or replace. An industry standard (what the field agrees on) lives only in the registry, `schemas/roles.json`; the packs apply it everywhere, and a project only waives it, with a reason and an expiry. |
| `fills` | list of string | no | The open choices it answers, each `<pack or skill>:<choice>`, such as `ci-pipeline:linter` (`aidd standard list` names them). Optional for the team's own standard. `aidd doctor` warns about a choice no pack or skill declares, and about two copies of library standards that fill one choice for one ecosystem. |
| `vendored` | mapping | no | Written by `aidd standard add` and `aidd stack add` for a copy of a library standard: never edit the copy. To change the rule, write your own standard and replace the library one in `standards_policy`. `aidd doctor` reports an edited copy and drift; `aidd upgrade` refreshes an unedited one. |
<!-- aidd:end -->

## Project constraints (`project`)

Humans set them. Agents read them before Specify and Review. `aidd gate --paths` and `aidd owners` print the stack radar and the rules for the paths in question, must first. A design fits `adopt` or `trial`. A `hold` item needs an ADR and a person's decision. A person approves a waiver, never an agent.

<!-- aidd:gen fields:config-project-rules -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | string | yes | Stable, unique name, such as `money-in-minor-units`; a waiver names it. |
| `level` | `must` \| `should` \| `may` | yes | How binding it is, in the BCP 14 sense (RFC 2119, RFC 8174): must, should (a reason to differ is written down), or may. |
| `statement` | string | yes | The rule, in one sentence. |
| `why` | string | yes | Why the rule exists, printed beside it. |
| `applies` | list of string | no | The paths it applies to. Omitted or empty: the whole repository. |
| `check` | string | no | The command or `tests` name that enforces it; without one it is a rule a reviewer checks. |
| `source` | string | no | The ADR or document that decided it. |
| `owner` | string | yes | The person or team who answers for it. |
| `review_due` | string | no | When its owner reviews it again; `aidd validate` warns once it has passed. |
<!-- aidd:end -->

<!-- aidd:gen fields:config-project-waivers -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `rule` | string | yes | The id of the rule it waives. |
| `reason` | string | yes | Why the rule cannot hold for now. |
| `approved_by` | string | yes | The person who approved it; never an agent or a bot account. |
| `until` | string | yes | The last day it holds. |
<!-- aidd:end -->

## Evidence (`.aidd/evidence/evidence.json`)

<!-- aidd:gen fields:evidence -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `aidd_version` | string | yes | The aidd release this record conforms to; the method and the toolkit share one version. |
| `head_sha` | string | yes | The commit the green results ran on. |
| `base_sha` | string | yes | The merge base the red results ran on. |
| `runner` | mapping | no | Which CI run produced this file. |
| `results` | list of mapping | yes | One entry per command and red_green run. |
| `spec_phase` | boolean | no | True when `aidd test` ran in the Spec phase: every changed path was the Spec or a file it freezes, and a Task had yet to change anything, so failing green results were expected. For people; the gate computes the phase from the diff itself. |
| `partial` | boolean | no | True when `aidd test --changed` ran only the commands the working-tree diff selects. A local convenience: the gate never accepts partial evidence. |
<!-- aidd:end -->
