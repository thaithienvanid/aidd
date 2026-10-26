# Config reference

This is the complete reference for `.aidd/config.yaml`, with every top-level key, then every table field by field. The tables are generated from `schemas/config.schema.json`, which is the source of truth. Check a config with `aidd validate .aidd/config.yaml`. Check the whole wiring with `aidd doctor`.

The gate always reads the config from the base branch, never from the change. Every file under `.aidd/` is a protected path, so a config change is itself a major change, as [METHOD.md §6](METHOD.md#6-routes) explains.

A minimal config:

```yaml
aidd_version: "1.0.0"
profile: team
owners:
  approvers: ["@your-org/leads"]
  specialists:
    security: ["@your-org/security"]
tests:
  - name: unit
    command: [npm, test]
```

## Contents

- [Top-level keys](#top-level-keys), and [parents, presets, and locks](#parents-presets-and-locks)
- The team, in [`owners`](#owners), [`owners.paths`](#ownerspaths), [`mission`, `goal`, and `agents`](#mission-goal-and-agents), [`standards`](#standards), and [`docs`](#docs)
- [`extends`](#extends) and [`targets`](#targets)
- Proof, in [`tests`](#tests), [`policy`](#policy), [`observe`](#observe), [`preview`](#preview), and [`evidence`](#evidence)
- Rules, in [`gates`](#gates), [`limits`](#limits), [`risk_rules`](#risk_rules), [`standard_changes`](#standard_changes), [`identities`](#identities), and [`emergency`](#emergency)
- Agent sessions, in [`guard`](#guard), [`guard.held_commands`](#guardheld_commands), and [`hooks`](#hooks)
- The project, in [`project`](#project), with its stack radar, budget, rules, and waivers

## Top-level keys

<!-- aidd:gen fields:config -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `aidd_version` | string | yes | The aidd release this record conforms to; the method and the toolkit share one version. |
| `profile` | `profile` | yes | Conformance profile. Each one is stricter than the one before. |
| `mode` | `enforce` \| `advisory` | no | Whether the guard and the gate block what the rules forbid (`enforce`) or only report it (`advisory`: an agent's edit outside the rules goes through with a note, and the gate never fails the merge). In both, no agent approves, merges, lands, or publishes for a person, changes their decision records, or rewrites the default branch. Unset, the profile's default: solo and team advise, org and audited enforce. The base branch's config wins over the CI setting. On GitLab, where anyone who may run a pipeline can set variables, only this key can make the gate advisory. A child config cannot relax a parent's `enforce`. |
| `components` | mapping | no | The parts of aidd that run in this repository. Each is on unless set to false, and each turns off alone: a part that is off says nothing, and the others keep working. The gate is set by `mode`, the session hooks by `hooks.level`, and the team by installing the aidd-team plugin. A child config cannot turn off a part its parent turns on. |
| `tenant` | string | no | The tenant this repository belongs to: the company, or an agency's client, that approves its changes. An org preset sets it; a child config cannot change a parent's tenant (a warning, and the parent's stands). The gate stamps it into every gate record, gate event, and change record, and approvals are scoped to it: an identity written `<tenant>:<login>` or `<tenant>:email:<address>` belongs to that tenant, an unqualified one to this tenant, and an approval by an identity of another tenant never counts. |
| `extends` | list of mapping (`extends`) | no | Parent configs merged first. A child may only tighten gates and cannot lower the profile. |
| `locks` | list of `disabled_rules` \| `rule_exclusions` \| `scope_exclude_paths` \| `changed_lines_exclude_paths` \| `standard_changes` \| `tenant` \| `project` | no | Set by a parent config (an org preset): keys its children may not add to or set. Each list key widens what passes; `tenant` binds the repository to its tenant; `project` binds the parent's `project`, which a child may then add to and tighten, never loosen. Children may add locks, never remove them. |
| `locale` | string | no | Agent-facing only: the BCP 47 tag an agent writes ticket titles and PR summaries in. aidd itself reads it nowhere, and the gate never does. Tokens stay English. |
| `specs_dir` | string | no | Where Spec files live. Default `specs`. A folder inside the repository, never its top: the Specs folder is a role's write area. |
| `proposals_dir` | string | no | Where proposals live, one folder each. Default `proposals`. A folder inside the repository, never its top: a change only to it needs no Spec. Keep a client's proposals in a repository only people cleared for that client can read. |
| `docs` | mapping | no | Linked documents: where `aidd new` writes them, which ones `aidd validate` asks for, and how old they may grow. |
| `owners` | mapping | no | Who owns and approves changes in this repo. |
| `mission` | string | no | The team's enduring purpose, set by humans, such as "small shops get paid on time". It changes rarely; `goal` is the current measurable target under it. `aidd list` shows it first in each Spec's why chain, and the session-start hook briefs the agent with it. A child config may replace it. |
| `goal` | string | no | The team's current measurable goal, set by humans, such as "make onboarding succeed on the first try": the target under `mission`. Agents weigh an open choice against it, `aidd observe --band` writes it into the draft Specs it opens, and `aidd list` shows it in each Spec's why chain. |
| `agents` | mapping | no | How the agents work in this repository: which roles may suggest work nobody asked for, and when they earn more autonomy. `aidd owners` shows the roles with the humans who decide. |
| `standards` | list of mapping | no | Standards: the team's own written rules and its copies of aidd's library standards (`aidd standard add`), each a Markdown document in the repository that agents read before a loop step, beside the standards their roles already apply. Each is opinionated (the default) or industry. `aidd owners` lists them by role with their type; `aidd doctor` checks each path, role, and `enforced_by` name, and each copy against the library. A child config adds entries; it cannot drop or redefine one a parent names. |
| `standards_policy` | mapping | no | A company's rules for library standards, usually in its org preset: `aidd standard add` and `aidd stack add` follow them and `aidd doctor` reports a breach. Only opinionated ids: an industry standard is never excluded or replaced, only waived per project, with a reason and an expiry. A child config adds and tightens: it cannot drop a parent's entry, require what a parent excludes, or allow a stack the parent does not. |
| `targets` | mapping | no | Delivery targets `aidd metrics --dora` checks the five DORA metrics against, and `aidd metrics` the loop-speed metrics. Set them from your own baseline, or from the latest DORA report's distribution; DORA advises comparing a service with its own past, not with other teams. |
| `tests` | list of mapping (`test_command`) | no | The repository suite, run on every change. Empty means Characterization: every Spec must bring its own commands. |
| `policy` | mapping | no | The Policy interface: org rules in any language, run from the base branch without credentials unless `pass_env` names them. |
| `publish` | `person` \| `agents` | no | Who takes work off this machine: a `git push`, a pull or merge request. `person`, the default: the team works on this machine (the inner loop and the local trunk), and only a person publishes, by typing `publish` or running `aidd publish`. The guard holds an agent's push and PR/MR until they do, and their record grants only a plain push of that branch to that remote. `agents`: for a team that works in pull requests, agents push their branches and open PR/MRs, and the platform's gate decides. Under both, a release, a tag, and a package stay the person's, and no agent merges or approves. Only a person changes it. |
| `observe` | mapping | no | The Observe interface. |
| `preview` | mapping | no | The one-command local preview: no hosting, no cost. The verifier starts it from a clean checkout of the head and records screenshots, a trace or video, and API transcripts under `.aidd/evidence/preview/<head_sha>/`, for people; the gate never reads it. `aidd init` fills it only when the command is obvious (a Docker Compose file). |
| `gates` | mapping | no | Overrides that may only tighten the profile. |
| `limits` | mapping | no | Work-in-progress limits for people: `aidd list`, `aidd doctor`, and autopilot read them, and the gate never does. Each may only tighten the profile and the parent config: 0 is off, the loosest, and a lower number (not 0) tightens. A child may set any value for a limit its parent left unset. |
| `risk_rules` | list of mapping | no | Path, dependency, and content rules that raise the required route, add dimensions, and name the specialist pool that reviews. |
| `disabled_rules` | list of string | no | Baseline risk rule names to turn off, such as `baseline:payments` in a repository with no payment code. Protected paths cannot be turned off; to keep a rule and drop one folder from it, use `rule_exclusions`. |
| `rule_exclusions` | mapping | no | Extra excluded paths for baseline rules, keyed by rule name. The recipe for a folder a rule matches by name that holds no such logic, such as UI components: `rule_exclusions: {"baseline:auth": ["src/components/permissions/**"]}` keeps permission badges out of the auth rule while src/auth/ stays major. Narrow a rule this way rather than disabling it. Protected paths have no exclusions. |
| `protected_paths` | list of string | no | Extra protected paths, added to the built-in set. |
| `scope_exclude_paths` | list of string | no | Paths any change may touch outside its scope, such as CHANGELOG.md. Never a catch-all. |
| `changed_lines_exclude_paths` | list of string | no | Paths not counted in the changed-line limit, such as lockfiles and generated code. Never a catch-all. |
| `standard_changes` | list of mapping | no | Pre-approved change classes that merge on green tests without a human. |
| `identities` | mapping | no | How platform accounts map to authors and agents. |
| `evidence` | mapping | no | Where the CI test run publishes evidence. |
| `emergency` | mapping | no | Emergency route settings. |
| `guard` | mapping | no | The guard (`aidd hook pre-tool`). Advisory, like the rest of the hook: it guides agents; the platform's own deploy protections decide. |
| `hooks` | mapping | no | The session hooks (`aidd hook session-start`, `aidd hook prompt-submit`, `aidd hook stop`, `aidd hook pre-compact`). Advisory helpers: they never use the network or a model (inside Orca, `orca_status` only calls the local `orca` CLI), and they allow whenever they cannot tell. |
| `autopilot` | mapping | no | Autopilot runs the AIDD loop between your decisions: aidd decides each next step and stops whenever a person must decide. These are its limits, which `aidd autopilot next` reads. Each has a default or is off, so nothing asks a question. |
| `project` | mapping | no | The project's constraints and rules, set by humans: a technology radar, the hosting, a budget, the team's own rules each with its why, and the waivers a person approved. Agents read them in Specify and Review; `aidd gate --paths` and `aidd owners` print the rules that apply to the paths in question, must first. `aidd validate` checks them; the gate never reads them. A parent that lists `project` in `locks` binds its rules, its hold list, its budget, and its hosting: a child may add rules and raise a rule's level, never lower one, waive a locked rule, or spend more. |
<!-- aidd:end -->

## Parents, presets, and locks

`extends` layers parent configs under this one. An org preset is the root parent of every repository config. You name it with `AIDD_ORG_PRESET`, or `org-preset-url` on the reusable workflow. When they merge:

- lists merge, scalars override, and every `gates` value keeps the strictest one
- a child cannot choose a weaker profile, or replace its parent's specialist pools, Policy, evidence source, or identity exemptions
- a parent's `locks` names widening keys that its children can't add to, such as `disabled_rules`, `rule_exclusions`, `scope_exclude_paths`, `changed_lines_exclude_paths`, and `standard_changes`. An org preset locks `disabled_rules`, `rule_exclusions`, and `scope_exclude_paths` without saying so
- a child that replaces its parent's `owners.approvers` gets a warning
- a child cannot relax a parent's `mode: enforce`, or turn off a part a parent's `components` turns on
- a child can't change a parent's `tenant`. The child gets a warning, and the parent's value stands. A parent may also lock it with `locks: ["tenant"]`. With a tenant, write an identity of another company as `<tenant>:<login>` or `<tenant>:email:<address>`. That identity's approvals never count here ([METHOD.md §8](METHOD.md#tenants))
- a preset's own parents are fetched by URL only, never from the repository, and a URL parent needs its `sha256`
- a parent's `locks: ["project"]` binds its `project`. A child adds rules and raises their level. A child never lowers a level, waives a locked rule, adopts what the parent holds, or spends more, as [`project`](#project) explains

## `components`

`components` names the parts of aidd that run here. Each is on until set to false, and each turns off alone. A part that is off says nothing, and the others keep working. The gate's switch is `mode`, and the session hooks' switch is [`hooks.level`](#hooks). The team is on when the aidd-team plugin is installed. `aidd doctor` prints which parts are on. [How-to](HOW-TO.md#use-only-the-parts-you-want) shows how to use only some of them.

<!-- aidd:gen fields:config-components -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `spec_steps` | boolean | no | The loop's Spec-first steps in the session: the route and next steps, the stop check, and autopilot. false: roles and skills work on the request directly, with no Spec or approval stops, and the guard allows every edit. It keeps only its rules on approving, merging, landing, publishing, the default branch, held commands, and loosening the config. The gate still judges each change unless `mode` is advisory. |
| `autopilot` | boolean | no | Autopilot. false: `aidd autopilot start` and `next` refuse, and nothing suggests it. It is off too while the Spec steps are off. |
<!-- aidd:end -->

## `owners`

`owners` says who may approve, and which specialist pools review high-risk changes. The table marks `approvers` as not required, because the schema accepts an empty list. But the gate fails closed on an empty list, so every profile, solo included, needs at least one Approver. Local-first, name yourself by the email your commits use, `email:you@example.com`.

<!-- aidd:gen fields:config-owners -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `default_owner_team` | string | no | owner_team that `aidd new` writes into new objects. |
| `approvers` | list of string | no | Eligible Approvers: users, @org/team, or `email:you@example.com` (local-first: the email your commits use). The schema accepts an empty or missing list, but the gate fails closed on it: every profile needs at least one Approver, and until then no change can merge. Under solo, `aidd init` fills in your own login or commit email. |
| `specialists` | mapping | no | Specialist Approver pools by name: `security`, `privacy`, `finance`, `compliance`, `data`, or any pool a risk rule names. A major change needs an approval from each pool its reasons name; an unbound pool falls back to `security`, so a financial major change (`baseline:payments`) goes to `finance` when it is bound and to `security` until then. Locked once a parent sets a pool. |
| `paths` | list of mapping | no | Per-path owners for monorepos. For every entry whose paths the change touches, at least one approval must come from that entry's approvers. |
| `codeowners` | boolean | no | Also read per-path Approvers from the base branch's CODEOWNERS (last matching rule wins), for Spec approval and Merge approval. Once a parent sets true, it stays true. |
| `backup_approvers` | list of string | no | Who to ask when a wait for an Approver passes `limits.escalate_after_minutes`: `aidd list` names them. Naming them changes nobody's eligibility: a backup approves only when they are an eligible Approver for the change. |
<!-- aidd:end -->

## `owners.paths`

`owners.paths` adds approvers for an area of a monorepo.

<!-- aidd:gen fields:config-owners-paths -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `paths` | list of string | yes | Globs this entry owns. |
| `approvers` | list of string | yes | Users or @org/team; one of them must approve a change that touches these paths. |
<!-- aidd:end -->

## `mission`, `goal`, and `agents`

`mission` is the team's enduring purpose, which changes rarely. `goal` is the current measurable target under the mission, one sentence the humans agree on. Every agent weighs an open choice against the goal. Where they show up:

- `aidd list` opens each Spec's why chain with both, followed by its Initiative, Epic, and hypothesis.
- The session-start hook briefs the agent with one `Mission: ... / Goal: ...` line.
- `aidd observe --band` writes the goal into the draft Specs it opens, so triage weighs a breach against it.
- `aidd doctor` warns when a team has none.

A child config may replace either. Each is a top-level key.

`agents` sets how the agents work.

- `proactive_roles` names the roles that may suggest work nobody asked for. They always suggest it as a draft Spec with `suggested_by: agent:<role>`. That Spec stays a draft until a person records its `triage` as accepted, declined, or snoozed. A duplicate is a relation, `duplicates`, never a triage decision. `aidd list` asks a person first, and `aidd validate` fails such a Spec past draft without `triage` ([METHOD.md §5.1](METHOD.md#51-status)).
- `agents.autonomy` sets the evidence `aidd metrics --autonomy` needs before it suggests less review.
- `delegate` says whether the main session hands its edits of repository content to an aidd-team role. The guard reads the role from `agent_type` in the hook input the harness writes, never from text an agent wrote. Role subagents are never affected.
  - `auto` is the default in every profile but audited. In the session that holds the autopilot lease, the guard denies the main session's edit and names the role that owns the file. In every other session, it allows the edit. When the team is installed, it tells the agent once per session and role which role owns the file. That is once per session and role, not once per Task as the first design said. The change is deliberate, so a long session isn't told again for each Task. The note is information, never a reason to refuse an edit. It never denies a person's own session.
  - With `always`, the guard denies that edit in every session. The audited profile starts at `always`, which applies only when the team is installed. Without the team, that default has no effect, so the guard acts as `auto`, and `aidd doctor` says so. An explicit `delegate: always` without the team still denies every such edit, and the deny says to install the team with `aidd init --team` or the aidd-team plugin. `aidd doctor` reports it as an error.
  - `never` does neither, and only a person sets it.
  - It doesn't govern running `aidd`, git branch, worktree, push, and PR/MR commands, reads, ignored files, or starting subagents. The guard holds the main session's obvious shell writes to the same rule, such as a redirect, `tee`, `sed -i`, `cp`, `mv`, `rm`, and `ln`, and its MCP file writes too. It judges each one in the repository that holds its target, so a sibling worktree is held too.

**The Claude Code advisor.** Claude Code can let a role consult a stronger model at decision points. aidd never sets it, and [TEAM.md](TEAM.md#the-claude-code-advisor) says what it costs and what it never replaces.

`aidd owners` shows the roles with [the humans who decide](ADOPTION.md#multiplayer-one-team-humans-and-agents).

```yaml
mission: small shops get paid on time
goal: make onboarding succeed on the first try

agents:
  proactive_roles: [product-manager, sre]  # default: product-manager, agile-coach, sre; [] means agents only work when asked
  delegate: auto  # default auto; audited always (with the team); never turns it off

  autonomy:
    min_changes: 20  # default 10
```

<!-- aidd:gen fields:config-agents -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `proactive_roles` | list of string | no | Agent roles that may suggest work nobody asked for, always as a draft Spec with `suggested_by: agent:<role>` that stays a draft until a person records `triage` (`aidd validate` enforces it). Default: product-manager (which also drafts Specs from incoming issues), agile-coach, and sre. An empty list means agents only work when asked. |
| `models` | mapping | no | The model each aidd-team role runs on, as `provider/model` (`anthropic/claude-opus-5-5`) or `inherit` (the session's model). Key it by tier (`reasoning` or `execution`) or by role name. A role's own entry wins over its tier's, so one role, such as the verifier, can run on any model by name. A key that names no tier and no role selects nothing, and `aidd doctor` warns about it. `aidd init --team` and `aidd upgrade` write it into each harness's own agent model field: Claude Code takes only an `anthropic/` model or `inherit` and Codex only an `openai/` one, OpenCode the whole `provider/model`, Kiro and Copilot the model name; where a harness cannot run it, the generated file says so and the harness's default runs, and `inherit` writes no model field outside Claude Code. Unset: the tier's default per harness. |
| `delegate` | `always` \| `never` \| `auto` | no | Whether the main session hands its edits of repository content to an aidd-team role. `auto`: in the session that holds the autopilot lease (`aidd autopilot start --session ID`), the guard denies the main session's edit and names the role that owns the file; in every other session it allows the edit and tells the agent which role owns it, once per session and role, when the team is installed. `always`: the guard denies that edit in every session; set explicitly without the team installed, it still denies, says to install the team (`aidd init --team`), and `aidd doctor` reports an error. `never`: neither. Role subagents are never affected. Not governed: running `aidd`, git branch, worktree, push, and PR/MR commands, reads, ignored files that git does not track, and starting subagents. Default by profile: `always` under audited, which applies only when the team is installed (without it the guard acts as `auto`, and `aidd doctor` says so), `auto` otherwise. A child config cannot loosen a parent's value. |
| `independent_review` | boolean | no | Ask for review on another model: `aidd doctor` warns when the Reviewer or the Verifier role resolves, through `models`, to the developer's model family (`anthropic/claude`, `openai/gpt`), or when `models` leaves one of them unset. The Reviewer and the Verifier start their reports with the harness and the model they ran on. Default false. |
| `autonomy` | mapping | no | When `aidd metrics --autonomy` suggests more autonomy for an agent and a kind of change. A group with any failed change or reworked Spec stays at the first stage. The report only suggests; a person decides. |
<!-- aidd:end -->

`agents.autonomy` sets the evidence `aidd metrics --autonomy` needs before it suggests less review for an agent and a kind of change.

<!-- aidd:gen fields:config-agents-autonomy -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `min_changes` | integer | no | Changes needed before the report suggests reviewing only the trade-offs. Default 10. |
| `min_first_pass` | number | no | Share of passed changes that passed on the first try, needed for that stage. Default 0.8. |
| `standard_min_changes` | integer | no | Changes needed before the report names the work a candidate standard change. Default 25. |
| `standard_min_first_pass` | number | no | First-try share needed for a candidate standard change. Default 0.9. |
<!-- aidd:end -->

## `standards`

`standards` holds the team's own rules beside the ones each role already applies, and its copies of aidd's library standards. Each names a Markdown document, and the aidd-team roles that read it before their step. Optionally, it also names the paths that make it apply, and the `tests` that enforce it.

- `type` is `opinionated`, the default and the only value a project writes. An opinionated standard is a choice that the team or the company commits to. An industry standard is what the field agrees on. It lives only in the registry, `schemas/industry-standards.json`, and the packs apply it everywhere. A project only waives one, with a reason and an expiry, so the config refuses `type: industry`.
- `fills` names the open choices it answers, such as `ci-pipeline:linter`. `aidd standard list` lists the open choices.
- `aidd standard add <id>` and `aidd stack add <name>` write a copy with its entry and its `tests`, as [STANDARDS.md](STANDARDS.md) explains. The entry's `from_library` mapping records the library id, aidd's version, and the hash of the copy.
- `aidd owners` lists them by role, with the type, marked "enforced by <test>" or "guidance". `aidd owners --json --changed <paths>` gives an agent exactly the ones to load for a change.
- `aidd doctor` warns about a missing document, an unknown role, or an `enforced_by` naming no test. For a copy, it also warns about an edit, a newer library version, and a deprecated or renamed id.
- A child config adds standards; it cannot drop or redefine one a parent names.

```yaml
standards:
  - name: api-errors
    path: docs/standards/api-errors.md
    roles: [developer, reviewer]
    when_changed: ["src/api/**"]
    enforced_by: [contract]  # a `tests` entry that checks the rule

  - name: writing
    path: docs/standards/writing.md
    roles: ["*"]  # guidance for every role
```

<!-- aidd:gen fields:config-standards -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | Stable name, shown by `aidd owners`, such as `api-errors`. |
| `path` | string | yes | The Markdown document that states the standard, repo-relative, such as `docs/standards/api-errors.md`. |
| `roles` | list of string | yes | aidd-team role keys that read it before their step, such as `developer` or `reviewer`, or `*` for every role. |
| `when_changed` | list of string | no | Load it only for a change that touches one of these paths. Omit to load it for every change. |
| `enforced_by` | list of string | no | Names of `tests` entries that check the rule, so the gate enforces it. Without one, the standard is guidance a reviewer checks. |
| `type` | `"opinionated"` | no | `opinionated`, the default and the only value here: a choice the team or company commits to, which a company can require, exclude, or replace. An industry standard (what the field agrees on) lives only in the registry, `schemas/industry-standards.json`; the packs apply it everywhere, and a project only waives it, with a reason and an expiry. |
| `fills` | list of string | no | The open choices it answers, each `<pack or skill>:<choice>`, such as `ci-pipeline:linter` (`aidd standard list` names them). Optional for the team's own standard. `aidd doctor` warns about a choice no pack or skill declares, and about two copies of library standards that fill one choice for one ecosystem. |
| `from_library` | mapping | no | Written by `aidd standard add` and `aidd stack add` for a copy of a library standard: never edit the copy. To change the rule, write your own standard and replace the library one in `standards_policy`. `aidd doctor` reports an edited copy and drift; `aidd upgrade` refreshes an unedited one. |
<!-- aidd:end -->

<a id="standards-policy"></a>

## `standards_policy`

`standards_policy` holds a company's rules for the library standards, usually in its org preset. `aidd standard add` and `aidd stack add` follow them, and `aidd doctor` fails on a breach.

- The policy takes opinionated library ids only, such as `python/uv-tooling`. aidd refuses an industry id there, because an industry standard is only waived per project, with a reason and an expiry.
- A child config adds and tightens. It cannot drop a parent's entry, require what a parent excludes or replaces, or allow a stack the parent does not allow.

```yaml
standards_policy:
  require: [python/uv-tooling]
  exclude: [python/mypy-typing]
  replace: {"python/ruff-lint-format": lint}  # the `standards` entry `lint` takes its place
  allow_stacks: [python-cli]
```

<!-- aidd:gen fields:config-standards_policy -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `require` | list of string | no | Library standards every project must carry; `aidd doctor` fails while one is missing. |
| `exclude` | list of string | no | Library standards no project may add. |
| `replace` | mapping | no | A library standard and the `standards` name of the company's own standard that takes its place, such as `python/mypy-typing: typing`. Projects cannot add the library one. |
| `allow_stacks` | list of string | no | The only stacks a project may add. Unset, any stack. |
<!-- aidd:end -->

`docs.max_runbook_age_days` sets how old a runbook's `tested_on` may be before `aidd doctor` warns, 180 days by default. Runbooks live in `docs/runbooks/` and postmortems in `docs/postmortems/`. `aidd new runbook` and `aidd new postmortem` write them, and `aidd validate` checks them.

## `docs`

Where the project's official docs live, and which documents a Spec should link, which `aidd validate` asks for. A Spec's own documents aren't official docs, because `aidd new <kind> <topic> --spec <ID>` writes each in the Spec's folder beside it, `specs/<ID>/`. The matrix only warns, because the gate never reads it, and nothing is asked of a minor or standard change. aidd owns each kind's rule, so a repository only sets a kind to `warn`, the default, or `"off"`. A child config can't turn off a kind its parent sets to `warn`.

```yaml
docs:
  dir: docs  # the official docs, such as docs/adr/NNNN-<topic>.md; a Spec's own documents go in specs/<ID>/
  max_review_age_days: 180  # aidd doctor warns on a living doc whose reviewed_on is older
  max_runbook_age_days: 180  # and on a runbook whose tested_on is older

  required:
    runbook: "off"  # never ask for a runbook; quote "off", or YAML reads it as false
```

<!-- aidd:gen fields:config-docs -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `dir` | string | no | Where `aidd new <kind> <topic> --spec <ID>` writes a linked document: `<dir>/adr/NNNN-<topic>.md` for an ADR, `<dir>/specs/<area or Spec id>/<kind>-<topic>.<ext>` otherwise. Default `docs`. |
| `required` | mapping | no | Which kinds of linked document `aidd validate` asks a Spec for: each kind `warn`, the default, or `off`. `warn` follows aidd's own rule for the kind, the same in every repository, and `aidd validate` only warns: it never errors, and the gate never reads it. A major Spec needs a tech-spec and a runbook (its own Alternatives considered and Pre-mortem, or Rollout, count) unless a protected path alone made it major, a threat-model when a risk dimension is security, privacy, or data, or, when compliance is on (`project.compliance` targets, or the audited profile), when a Task touches an authentication, authorization, secrets, or cryptography path (on normal too), an authz doc (the authorization matrix) when a Task touches an authentication or authorization path (the `baseline:auth` paths) and the risk names security or compliance is on (on normal too), a design spec (`design-spec`, or `design.files`) on a feat whose Tasks touch a user-facing path, a test-plan only on a trigger (a compliance dimension or type, the audited profile, a device path, `uat: true`, or 10 or more Acceptance items), a migration doc on a data dimension or type or an irreversible change, a compliance doc (its DPIA) when a risk dimension is privacy (on normal too), with the data map (`data-map`) suggested beside it, and an analytics doc (a tracking plan) when the Spec has a `hypothesis` (on normal too); on normal the design-spec, test-plan, and migration rules are suggestions `aidd new spec` prints. Otherwise testing lives in the Spec's Acceptance and the tech spec's Test strategy. A child config cannot set `off` for a kind its parent sets to `warn`. |
| `exemplars` | list of string | no | The project's best Specs, which a person names, such as `["specs/SPEC-12.md"]`. `aidd context` lists them for the Specify step, and whoever writes a Spec reads them first, for their shape and depth, never to copy them. `aidd validate` warns on a path that does not exist. aidd never chooses them. |
| `max_review_age_days` | integer | no | Days after a living doc's `reviewed_on` date before `aidd doctor` warns that it is stale. Default 180, about six months. The living docs are the architecture overview, the data map, the vendor register, the glossary, and every doc a Spec links with `frozen: false`, except a runbook, which has `tested_on`. `reviewed_on` is optional: a person sets it in the doc's `---` YAML front matter each time they review the doc. A doc nobody has reviewed lately describes a system that has moved on. |
| `max_runbook_age_days` | integer | no | Days after a runbook's `tested_on` date before `aidd doctor` warns that it is stale. Default 180. A runbook nobody has run lately is a guess at the moment it is needed. |
<!-- aidd:end -->

## `extends`

Each entry names one parent config.

<!-- aidd:gen fields:config-extends -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `path` | string | no | Repo-relative path to a parent config: no leading / or ./, no .., backslashes, or wildcards. |
| `url` | string | no | HTTPS URL of a parent config. |
| `sha256` | string | no | Required with url. Pins the content. |
<!-- aidd:end -->

## `targets`

`targets` sets the delivery targets. `aidd metrics --dora` checks the five DORA software delivery metrics against them. `aidd metrics` checks the loop-speed metrics against them, such as time to first feedback, approval wait, and flow efficiency. Either exits 1 when one is missed, so a scheduled job can raise it. Set them from your own baseline first, then tighten them. Every year, DORA publishes how its survey respondents are distributed on each metric. DORA advises comparing a service with its own past, not with other teams. `max_cost_per_change` is display only. `aidd metrics --cost` warns for each change over it and shows whether it's met, but never exits 1 for it.

```yaml
targets:
  min_deployments_per_week: 10
  max_lead_time_hours: 24
  max_change_fail_rate: 0.1
  max_recovery_days: 1
  max_rework_rate: 0.05
  max_first_feedback_minutes: 30
  max_approval_wait_p90_minutes: 1440
  min_flow_efficiency: 0.4
  max_cost_per_change: {amount: 5, currency: USD}
```

<!-- aidd:gen fields:config-targets -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `min_deployments_per_week` | number | no | At least this many changes passing the gate per week. |
| `max_lead_time_hours` | number | no | At most this many median hours from a change's first gate run to its first pass. |
| `max_change_fail_rate` | number | no | At most this share of released Specs rolled back or failing observe. |
| `max_recovery_days` | number | no | At most this many median days to restore a failed release. |
| `max_rework_rate` | number | no | At most this share of passed changes on the emergency route. |
| `max_first_feedback_minutes` | number | no | At most this many median minutes from a head's push to the first gate decision holding its test results. `aidd metrics` exits 1 when missed. |
| `max_approval_wait_p90_minutes` | number | no | At most this many minutes at the 90th percentile of the slowest approval's wait (Spec approval, Merge approval, specialist approval). `aidd metrics` exits 1 when missed. |
| `min_flow_efficiency` | number | no | At least this share of lead time (opened to first pass) not spent waiting on a human approval. `aidd metrics` exits 1 when missed. |
| `max_cost_per_change` | mapping | no | At most this agent cost for each change in `aidd metrics --cost`: it warns for each change over it, and the target is met when none is. Display only: never a gate rule, never pauses work, never sets the exit code. |
<!-- aidd:end -->

## `tests`

`tests` is the repository suite, run on every change beside the Spec's own tests. Empty means every Spec brings its own commands, as Characterization in [METHOD.md §10](METHOD.md#10-scale-modules) describes. Each entry is a test command. `new_behavior` belongs to a Spec's tests and is never set here.

aidd starts a command with no shell, so a command that needs an environment variable starts with `env`, as in `[env, PYTHONPATH=src, python3, -m, pytest]`. `aidd init` and `aidd validate` refuse a command whose first word is `NAME=value`, since that word would run as the program.

<!-- aidd:gen fields:test_command -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | Stable name used in evidence. |
| `command` | list of string | yes | Command vector, one argument per item. Never a shell string. |
| `new_behavior` | boolean | no | True when this command proves new or fixed behavior. It must fail on the base commit (red) and pass on head (green). |
| `timeout_seconds` | integer | no | Wall-clock limit. A timeout is a fail. Default 1800. |
| `smoke` | boolean | no | In the config's `tests`: part of the smoke set, the only repository commands an emergency change runs (with its own). When no command is marked, an emergency runs the whole suite. |
| `retries` | integer | no | How many more times a failing run on head is tried (default 0). Every attempt is kept in the evidence; a pass after a failure passes, marked flaky, and metrics count it. A red run on the base commit is never retried. |
| `when_changed` | list of string | no | Run and require this command only when a changed path matches. Omit to run it on every change. |
| `covers` | list of string | no | In a Spec: the Acceptance items this command proves, by id (`A1`, `A2`, ...). Optional; once any command declares it, `aidd validate` warns about an Acceptance item no command covers, and about an id the Acceptance section does not have. Under `tests.mode: with_code` every item must be covered, or the Spec is invalid; otherwise the gate never reads it. |
<!-- aidd:end -->

## `policy`

`policy` is your own command the gate runs for freezes and deny lists.

<!-- aidd:gen fields:config-policy -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `command` | list of string | no | Prints allow, deny, or freeze, or a JSON answer with findings. No output or a timeout is deny. Locked once a parent sets it. |
| `pass_env` | list of string | no | Credential-like variables (names with TOKEN, SECRET, PASSWORD, KEY, or CREDENTIAL) the Policy command may see, by name; every other one is dropped from its environment, as for the test commands. Locked once a parent sets it. |
<!-- aidd:end -->

## `observe`

`observe` is the post-release health check.

<!-- aidd:gen fields:config-observe -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `command` | list of string | no | Default post-release check when a Spec's observe block names none. |
| `bands` | list of mapping | no | Control bands for `aidd observe --band`: a metric judged against its recent baseline. Detection is deterministic; the tier sets what an agent may do (log, diagnose read-only, propose a change through the gate). |
<!-- aidd:end -->

## `preview`

`preview` is the one command that starts the app on this machine with seed data. With it, the verifier can exercise each Acceptance item on the exact head, before anyone pays for an environment. `aidd init` writes it when a Docker Compose file makes the command obvious, and a commented example otherwise.

```yaml
preview:
  command: [docker, compose, up, --build]
  url: http://localhost:3000
```

The verifier runs it from a clean checkout of the head commit, in a git worktree. It saves what it saw under `.aidd/evidence/preview/<head-sha>/`. `aidd record artifacts <head-sha>` then writes `artifacts.json` in that folder, which lists each file with its kind and SHA-256 in the `schemas/artifacts.schema.json` format, so the verifier stays read-only. The Merge approval page shows the files. They're for people reading the verification report, because the gate decides on exit codes only. [Platforms](PLATFORMS.md#environments-local-preview-first) says which environment proves what.

<!-- aidd:gen fields:config-preview -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `command` | list of string | yes | Starts the app on this machine with its seed data (the command loads them), from a clean checkout, such as ["docker", "compose", "up", "--build"]. The verifier runs it in a worktree of the exact head commit. |
| `url` | string | no | Where the running preview answers, such as http://localhost:3000: the address the verifier drives. |
<!-- aidd:end -->

## `gates`

Each value may only tighten the profile.

<!-- aidd:gen fields:config-gates -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `separation_of_duties` | boolean | no | Approvers must differ from the change's authors. Only true tightens. |
| `spec_approval_required_routes` | list of `route` | no | Routes that need Spec approval before implementation. |
| `specialist_spec_approval` | boolean | no | Each required specialist pool also approves the Spec on major. |
| `approvals` | mapping (`route_ints`) | no | Approvals needed at Merge approval, per route. |
| `specialist_approvals` | integer | no | Approvals needed from each required specialist pool on major, and on emergency changes that touch protected paths. |
| `policy_required_routes` | list of `route` | no | Routes that fail without a bound Policy command. |
| `provenance` | `declare` \| `every_commit` | no | declare: assisted_by lists every agent a commit names (an `Assisted-by:` trailer, or a `Co-authored-by:` agent). every_commit: also, every non-merge commit carries an `Assisted-by:` trailer (`Assisted-by: none` when no agent wrote it). |
| `red_green` | `warn` \| `require` | no | warn or require that new-behavior tests fail on base. |
| `standard_changes` | boolean | no | Allow configured standard changes. Only false tightens. |
| `observe_required_routes` | list of `route` | no | Routes whose Spec must have an observe block. |
| `max_changed_lines` | mapping (`line_limits`) | no | Maximum changed lines per route, after changed_lines_exclude_paths and the files Spec approval froze. The standard and emergency routes have no changed-line limit. |
| `unlinked_authors` | `warn` \| `fail` | no | A commit author the platform cannot map to an account might be an Approver: warn, or fail. Only fail tightens. |
| `spec_approval_proof` | `optional` \| `require` | no | optional: an approval line may name the commit it was given on, and the gate records whether Spec approval came before implementation. require: only such approvals count, on a commit that changed nothing but the Spec and its frozen files. Only require tightens. |
| `approval_carry` | `trivial_rebase` \| `none` | no | Whether a Merge approval of an earlier head counts for the new head after a trivial rebase (Gerrit's TRIVIAL_REBASE): the change's diff is identical, byte for byte apart from line offsets, onto a base that descends from the approved one on the protected branch; nobody new committed; no protected path changes; the tests run again on the new head as usual. none: every new head needs a new approval. The emergency route never carries. Only none tightens. |
| `approval_carry_routes` | list of `route` | no | The routes on which `approval_carry` applies; emergency never does. A shorter list tightens. |
| `local_approvals` | `any` \| `signed` | no | Local-first approvals (`aidd approve`, read by the local gate and `aidd land`): any counts every recorded approval; signed counts only those whose git signature verifies as good (with SSH signing, from the Approver's own email principal). Read from the base branch, so an agent cannot switch it off. Only signed tightens. |
| `local_signers` | string | no | The repository file listing whose SSH signatures count as local approvals, in git's allowed signers format (one `<email> <public key>` line per Approver), read from the base branch's tip and never from the working tree or this machine's git config (default `.aidd/allowed_signers`). The check pins its own settings (SSH signatures, ssh-keygen, this file), so an agent's edit to the machine's gpg config changes nothing. Under `local_approvals: signed` with no such file on the base branch, no local approval counts. A parent config's path stands. |
<!-- aidd:end -->

## `limits`

`limits` holds the work-in-progress limits for people. `aidd list`, `aidd doctor`, and autopilot read them, and the gate never does.

- `max_open_per_approver` is the most open approval waits one Approver should hold. It is 3 under team, org, and audited, and off under solo.
- `escalate_after_minutes` sets when `aidd list` marks a wait and names `owners.backup_approvers`. It is off by default.
- `max_in_progress_per_owner` is the work-in-progress limit, the most Specs in progress one `owner` should hold. It is off by default.
- `max_in_progress_days` is the work item age after which `aidd list` flags a Spec in progress as aging. Unset, it is 10.
- `max_goal_age_days` is the age after which `aidd list` and `aidd doctor` warn about a goal branch. A long integration branch drifts from the default branch. Unset, it is 7.
- `max_branch_age_days` is the age after which they warn about any other branch with unmerged work. Trunk-based teams merge at least daily. Unset, it is 2.
- `max_open_branches` is how many branches with unmerged work they allow before a warning. Unset, it is 3, DORA's mark.

For each, 0 is off and a lower number tightens. A child may set any value for a limit its parent left unset. So an org preset that wants `max_in_progress_days` enforced must set it explicitly.

<!-- aidd:gen fields:config-limits -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `max_open_per_approver` | integer | no | The most open waits (Spec approval or Merge approval) one Approver should hold; 0 turns it off. `aidd list --waiting-on-me` and `aidd list` warn when an Approver holds more, and autopilot starts no new work while one does. |
| `max_in_progress_per_owner` | integer | no | The work-in-progress limit: the most Specs in progress one `owner` should hold; unset or 0 is off. `aidd list` warns when a person holds more. |
| `max_in_progress_days` | integer | no | Work item age: the most days a Spec should stay in progress before `aidd list` flags it as aging (`aged`). Unset is 10; 0 turns the flag off, and the age still shows. Set it from your own cycle time, such as its 85th percentile. |
| `max_branch_age_days` | integer | no | Branch age, for trunk-based work: the most days a branch with work the default branch lacks should live before `aidd list` and `aidd doctor` warn, counted from its oldest own commit. Unset is 2 (DORA: hours, merged at least daily; an agent's branch also waits on a person's approvals); 0 turns the warning off. Land the work, behind a flag when it is unfinished, or split it. |
| `max_open_branches` | integer | no | Open branches, for trunk-based work: the most local branches with work the default branch lacks (goal branches aside; a branch whose work another open branch holds, such as a Task branch merged into its Spec's, counts as that branch) before `aidd list` and `aidd doctor` warn. Unset is 3, DORA's mark; 0 turns the warning off. |
| `max_goal_age_days` | integer | no | Goal age: the most days a goal branch (`goal/<name>`) should live before `aidd list` and `aidd doctor` warn, counted from its oldest commit the default branch lacks. Unset is 7; 0 turns the warning off. A long integration branch drifts from the default branch: release what is integrated, or split the goal. |
| `escalate_after_minutes` | integer | no | Minutes a Spec may wait for an Approver before `aidd list` marks the wait escalated and names `owners.backup_approvers`; 0 turns it off. It never approves anything. |
<!-- aidd:end -->

## `risk_rules`

`risk_rules` names paths that raise the route or name a specialist Approver pool.

<!-- aidd:gen fields:config-risk_rules -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | Rule name, shown in findings and usable in rule_exclusions and disabled_rules. |
| `paths` | list of string | no | Globs that trigger the rule. A rule names `paths`, `dependencies`, `content`, or a mix. With `content`, the paths only narrow where its patterns are read: a path alone never triggers it. |
| `content` | list of string | no | Regular expressions (Python `re`, searched in each line) that trigger the rule when a line the diff adds matches one, in a file its `paths` match (any file without `paths`) and its `exclude` does not. What the code does, wherever it sits: a raw SQL string, a call to a model API, a new outbound host. The adapter reads the diff with git and sends the matches in the context (`content_matches`); `aidd gate --paths` cannot see content, so a plan's forecast never shows them. A pattern that does not compile is a config error. |
| `dependencies` | list of string | no | Dependency names that also trigger the rule when the diff adds one to a manifest (package.json, requirements*.txt, pyproject.toml, Pipfile, go.mod, Cargo.toml, pom.xml, build.gradle(.kts), *.csproj, Gemfile, composer.json, pubspec.yaml, mix.exs, or a Django settings module's INSTALLED_APPS), wherever the code that uses it sits. A name matches ignoring case and treating `-`, `_`, and `.` alike; one ending in `/` matches every name it starts (an npm scope or a Go module path). A version change never matches, and `exclude` applies to the manifest's path. |
| `route` | `minor` \| `normal` \| `major` | no | Minimum route when the rule matches; without it, only the dimensions raise the route. |
| `dimensions` | list of `dimension` | no | Risk dimensions the change must declare when the rule matches. |
| `specialists` | list of string | no | Specialist Approver pools that must approve the head. A rule below major asks them whenever it matches, on every route (an emergency too, unless it is an exact revert): a pool asked for what the change does, not only for its size. A rule that forces major asks them through the major route. Default: the pools its dimensions name, else `security`, and only when the rule makes the change major. |
| `exclude` | list of string | no | Paths this rule never matches. |
<!-- aidd:end -->

## `standard_changes`

`standard_changes` names bot changes that merge on green tests with no human.

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

## `identities`

`identities` lists bot and system accounts, which can never approve.

<!-- aidd:gen fields:config-identities -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `system_accounts` | list of string | no | Platform bookkeeping accounts that are never authors, such as web-flow. Only bot-like accounts (`*[bot]`, web-flow, github-actions) are accepted. |
| `bots` | list of string | no | Agent accounts that act as implementers. They can never approve, and their commits count as agent-written for provenance. |
<!-- aidd:end -->

## `evidence`

`evidence` says where the gate finds test results.

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

## `emergency`

`emergency` sets deadlines for the review that follows a production repair.

<!-- aidd:gen fields:config-emergency -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `review_sla_days` | integer | no | Longest allowed gap between the day an emergency change opens and its review_due. Default 2. A child takes the smaller value. |
<!-- aidd:end -->

## `guard`

`guard` lists commands the guard hook holds for a person, such as a production deploy.

<!-- aidd:gen fields:config-guard -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `held_commands` | list of mapping | no | Shell commands the guard hook denies to every agent until a person approves them, such as a production deploy. `aidd init` writes one, named `init: ...`, for each deploy script, Makefile deploy target, and infrastructure tool command it finds; a person may delete any. A child config adds held commands to its parents'; it cannot drop or redefine one a parent names. |
<!-- aidd:end -->

### `guard.held_commands`

`guard.held_commands` lists shell commands that wait for a person, such as a production deploy. With them, you tier autonomy per environment, so agents run the build and staging freely, and a person allows production.

`aidd init` writes an active entry for each deploy command it finds, because agents never deploy. It holds each script named `deploy*`, `rollout*`, or `provision*`, since provisioning buys paid infrastructure, and each Makefile target named so. It does not hold `release*` names by default, because a release script is often a local build. For each infrastructure tool that the repository's files show, it holds the commands that change or destroy infrastructure. Examples are `terraform apply` and `destroy`, `pulumi up`, `cdk deploy`, and `wrangler deploy`. These entries hold the command for every environment, staging too. Each entry's name starts with `init:`, and a comment says that a person may delete it. To let a staging deploy run, a person narrows the entry to production, such as `match: ["wrangler* deploy *", "--env production"]`. Or the person deletes the entry. Re-running `aidd init` keeps the config as it is, and `aidd upgrade` changes only `aidd_version`. So a deleted entry stays deleted, except after `aidd init --force`, which rewrites the config. `aidd doctor` lists each held command.

- **What is held.** The guard hook, `aidd hook pre-tool`, denies a matching Bash command to every agent, the session, a role, or a helper. The Claude Code plugin and `aidd init --claude-hooks` wire it.
- **Until when.** Until the variable named in `requires` holds a non-empty value in the environment Claude Code started with. A person sets it when they allow the deploy.
- **Why an agent cannot.** The hook reads the environment Claude Code gave it, not the agent's shell. And the hook denies a command that names the variable itself.

```yaml
guard:
  held_commands:
    - name: production deploy
      match: [deploy, production]  # all must match one simple command, ignoring case
      environment: production
      requires: RELEASE_APPROVAL  # the Approver starts the session with RELEASE_APPROVAL=CHG-1234 claude
      message: "Production deploys need a change ticket from #release."

    - name: terraform apply
      match: ["terraform apply*"]  # a glob; no `requires`, so agents never run it
```

A production flag flip is a release decision, so a person makes it, as with a deploy. Hold the command or script your flag system flips with. When the flags live in a file, as flagd's do, make the production flag file a `protected_paths` entry instead. Then a flip is a major change through the gate.

```yaml
guard:
  held_commands:
    - name: production flag flip
      match: [flag, production]  # such as `./scripts/flags set checkout-v2 on --env production`
      environment: production
      requires: FLAG_APPROVAL
      message: The flag's owner flips it in production.
```

The hook matches each simple command of the line, following `&&`, `;`, `|`, `cd`, and `sh -c`. So `echo deploy; ls production` doesn't match, and `cd infra && make deploy ENV=production` does. The matching is best-effort parsing and advisory, like the rest of the hook. It also reads each command as the program it runs, so `sh scripts/deploy.sh` matches `deploy.sh *`. The hook does not see a deploy started from a script whose name matches nothing, or from inline interpreter code. The hook catches the ordinary ways an agent runs a command, not deliberate evasion, such as ANSI-C quoting, variables, command substitution, or `eval` tricks. Keep the platform's own protection as the control, such as a GitHub environment with required reviewers, or a GitLab protected environment. Use held commands to stop the agent before it asks the platform.

<!-- aidd:gen fields:config-guard-held_commands -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | Gate name, shown in the deny message. |
| `match` | list of string | yes | Patterns that must all match one simple command, ignoring case: a pattern with `*`, `?`, or `[` is a glob over the whole command, any other a substring. ["deploy", "production"] matches `make deploy ENV=production`. A glob that ends in ` *` also matches a command that ends just before it, so `make* deploy *` matches `make deploy` and never `make deployment`. The hook also reads the command as the program it runs. It skips environment assignments, wrappers such as sudo, and runners such as npx. It cuts the program's path to its name, takes a script run by an interpreter as the script, and leaves out NAME=value words. So `terraform* apply *` matches `AWS_PROFILE=prod ./bin/terraform apply`. |
| `unless` | list of string | no | Patterns read like `match`: the entry does not hold a command that any of them matches, such as ["vercel build *"]. |
| `environment` | string | no | Label of the environment the command reaches, such as production or staging, shown in the deny message. |
| `requires` | string | no | Environment variable a person sets to a non-empty value, in the environment Claude Code starts with, to approve the command, such as RELEASE_APPROVAL. A command that names the variable itself is denied. Without it, agents never run the command. |
| `message` | string | no | Extra text for the deny message, such as where to ask for approval. |
<!-- aidd:end -->

## `autopilot`

Autopilot runs the AIDD loop between your decisions; aidd decides each next step and stops whenever a person must decide, as [Autopilot](AUTOPILOT.md) and [METHOD §5.3](METHOD.md#53-autopilot) explain. `autopilot` holds its limits, which `aidd autopilot next` reads each turn. No limit asks a question, because each one has a default or is off.

```yaml
autopilot:
  timebox: "8h"  # default 6h; the lease ends then
  max_tokens: 400000  # optional; no default
  max_cost: {amount: 20, currency: USD}  # optional; only notes in this currency count
  retro_every: 5  # optional: a retro after 5 merged changes
```

A token or cost cap counts only what `aidd autopilot note --tokens` and `--cost` record. The autopilot command reports that spend itself, so the caps guide a cooperating autopilot, and the person and the gate stay the controls. Many people pay by plan, not by token, so neither cap has a default.

<!-- aidd:gen fields:config-autopilot -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `timebox` | string | no | How long one run may last, such as `90m` or `2h`. `aidd autopilot start` sets the lease to end then, and `aidd autopilot next` stops at that time. Default `6h`. |
| `max_tokens` | integer | no | The most tokens one run may record with `aidd autopilot note --tokens`. `aidd autopilot next` stops the run when the total reaches it. No default. |
| `max_cost` | mapping | no | The most one run may cost, from the costs `aidd autopilot note --cost` records. `aidd autopilot next` stops the run when the total reaches it. No default. |
| `retro_every` | integer | no | Run `/aidd-team:retro` after this many merged changes, counted since the last retro the journal records. Off when unset. |
| `parallel` | integer | no | How many Specs one turn may work on at once. `aidd autopilot next` returns its action and, in `also`, up to this many minus one more agent steps, each on another Spec whose Tasks' scopes overlap none of the others. Each runs in its own worktree on its Spec's branch. Approvals and lands never run in parallel. Default 2. |
| `notify` | list of string | no | A command aidd runs, with the message as its last argument, once each time a run stops for a person: a decision waits, it is blocked, a limit ended it, or it finished. For a run nobody watches, such as `["ntfy", "publish", "my-topic"]` or `["osascript", "-e", "display notification (system attribute \"AIDD_NOTICE\")"]`. A vector, never a shell string; the message is in AIDD_NOTICE too. Off when unset. |
<!-- aidd:end -->

## `hooks`

`hooks` sets the Claude Code session hooks, which the aidd plugin and `aidd init --claude-hooks` wire beside the guard. They're advisory helpers. They're deterministic, use no model and no network, and allow whenever they can't tell or fail.

- `aidd hook session-start`, on SessionStart, adds a summary of this change to the agent's context, at most 15 lines, led by its route. After a compaction, at balanced and above, it adds a reminder to write the handoff note into the Spec or the PR/MR. The handoff note has the lines Done, Next, Needs, Stopped at, and an optional Spend. After a compaction or on a resume, it also reads back the state that pre-compact saved.
- `aidd hook prompt-submit`, on UserPromptSubmit, adds one line to the agent's context with each prompt. The line names this change's first step, who takes it, and its command. It runs only under the team and org profiles, at balanced and above. It costs a few tokens, masks secret-looking values, and never blocks a prompt.
- `aidd hook stop`, on Stop and on SubagentStop for an aidd-team role that writes code, checks the evidence when an active Spec has changes in its Tasks' scope. If no evidence file records the tests as passed on HEAD, it tells the agent to run `aidd test` and report the result. The evidence file is `.aidd/evidence/evidence.json`, or the `evidence.artifact` folder. The tests are every applicable `tests` command and the Spec's `tests.commands`. Once Spec approval holds, the stop hook also runs the guard's rules over every path the branch changed. It names each change that the guard would have denied. Such a change is a frozen test, design file, or doc edited since, a path outside the scope, or a protected path. A script or a shell command could write such a change without the edit hook seeing it. At balanced, the agent gets the reminder once. At strict, the hook blocks the stop once with that reason. It never continues an agent a stop hook already continued.
- Inside [Orca](ORCA.md#the-workspace-card), session-start and stop also write this change's first step on the worktree's Orca card, through the `orca` CLI. It is display only, never evidence. It gives up after 2 seconds, and does nothing outside Orca. `orca_status: false` turns it off.
- `aidd hook pre-compact`, on PreCompact, saves the state of the work in the git directory, as `.git/aidd/snapshots.json`, never in a tracked file. The state is the summary of this change, the latest handoff note's `stopped_at`, and this session's autopilot lease and last steps. Claude Code's PreCompact output cannot add context, so the hook prints nothing, and session-start reads the state back after the compaction. It runs at balanced and above.

The level turns the prompt hint, the stop check, and the compaction note on and off together, so `level: minimal` is how you turn them off. The summary runs at every level but `"off"`, which silences every session hook. The guard isn't a session hook, so it keeps its rules at every level.

```yaml
hooks:
  level: strict  # off, minimal, balanced, or strict; default: solo minimal, team and org balanced, audited strict
```

A child config cannot lower its parent's level, or the level its parent's profile starts at. The guard logs each deny to `guard.jsonl` in `.git/aidd/`, the git directory every worktree shares and git never commits. `aidd metrics --guard` counts them by reason and by role.

<!-- aidd:gen fields:config-hooks -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `level` | `off` \| `minimal` \| `balanced` \| `strict` | no | How much the session hooks do. off: none of them speaks, and the guard keeps every rule. minimal: `aidd hook session-start` adds a summary of this change: its route and next steps. balanced: also the stop reminder (`aidd hook stop`, for Stop and SubagentStop, asks the agent once to run `aidd test` when in-scope changes have no passing evidence on HEAD, and names each change the guard would have denied once Spec approval holds); the compaction note (`aidd hook pre-compact` saves the state of the work in the git directory, never in a tracked file, and after a compaction or on a resume session-start reads it back with a reminder of the handoff note); and, under the team and org profiles, the prompt hint (`aidd hook prompt-submit` adds one line with this change's first step to each prompt, and never blocks one). strict: the stop reminder blocks the stop instead. Default by profile: solo minimal, team and org balanced, audited strict. A child config cannot lower a parent's level. |
| `orca_status` | boolean | no | Inside Orca, with its `orca` CLI on PATH, put this change's first step on the worktree's Orca card (its comment) when session-start and stop run. Display only, never evidence or an approval; time-boxed to 2 seconds and silent on failure. Does nothing outside Orca. Default true. |
<!-- aidd:end -->

## `project`

The project's constraints and rules, set by humans and read by agents. What they are for, a worked example, and how waivers work are in [ADOPTION.md](ADOPTION.md#project-constraints-and-rules). `aidd validate` checks them. The gate never reads them.

<!-- aidd:gen fields:config-project -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `repo` | string | no | The GitHub repository this config belongs to, as `owner/name`. `aidd init` writes it from `origin`. Autopilot trusts the platform's approvals only from it, read from the base branch. |
| `work` | `product` \| `client` | no | Whose work the repository holds: `product`, the team's own product (the default), or `client`, work for a client. With `client`, `aidd autopilot next` starts a goal with `/aidd-team:propose`, not `/aidd-team:plan`. |
| `stack` | mapping | no | A technology radar: what new work uses. A child config adds to each list. |
| `hosting` | string | no | Where the project runs, in a phrase, such as "one VPS in the EU". Agents design and deploy for it. |
| `dev_services` | mapping | no | The project's dev services, shared by every worktree on this machine. aidd gives each command it runs (`aidd test`, the teardown) AIDD_WORKTREE, a stable name per worktree, so the project names its database, bucket, and ports by it. |
| `budget` | mapping | no | What running the project may cost. The SRE picks the zero-cost option that fits first. |
| `rules` | list of mapping (`project_rule`) | no | The team's own rules. `aidd validate` fails on a repeated id and warns once a rule's `review_due` has passed. |
| `waivers` | list of mapping (`project_waiver`) | no | Time-boxed exceptions to a rule. `aidd validate` fails on a waiver of an unknown rule or one an agent or bot approved, warns 14 days before `until`, and fails once it has passed. |
| `defaults` | mapping | no | What every product gets unless a person turns it off: each default is on unless `disabled` names it, with the reason (`disabled: {dark_mode: a print-only report}`). Agents build them on the MVP's Day 0 and whenever a change touches the area, from `aidd-team:product-defaults`, which owns each one and its test. `aidd init` writes the list commented, and in a repository it detects as a command-line tool or a library (no web or mobile interface) turns the interface defaults off with the reason "no user interface". A child's `disabled` replaces its parent's; when the parent locks `project`, the child may only drop keys (turn a default back on), never add one. |
| `compliance` | mapping | no | What the product must be ready for. Compliance is on when `targets` names a framework or law, or when the profile is `audited`: `aidd gate --paths` names the `enterprise-controls` pack, `aidd validate` warns for a threat model and an authorization matrix on security and auth paths (`docs.required`), and `aidd init` writes the security-scanning workflow. The organizational work (policies, an ISMS, vendor reviews, training, a penetration test, the auditor) stays with people outside the team. `aidd validate` warns when a target that expects separation of duties (soc2, iso27001, pci-dss, fedramp, hipaa) meets the `solo` profile, which waives it. `aidd init` writes this table commented out unless given `--compliance-target`. A parent that locks `project` keeps its targets: a child adds to them. |
| `writing` | mapping | no | How the project's documents are written. It only records an opt-in for the humans and agents who write them; no check, rule, or gate reads it. A parent that locks `project` keeps its kinds: a child adds to them. |
<!-- aidd:end -->

`project.stack`, the technology radar:

<!-- aidd:gen fields:config-project-stack -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `adopt` | list of string | no | The default for new work. |
| `trial` | list of string | no | In use on a trial basis: fine where the design says why. |
| `hold` | list of string | no | Not for new work without an ADR that records a person's decision. `aidd validate` warns when a Spec's Context or Design names one and the Spec links no ADR (a case-insensitive text match: a hint, never a gate rule). |
<!-- aidd:end -->

`project.budget`:

<!-- aidd:gen fields:config-project-budget -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `max_infra_per_month` | number | no | The most the infrastructure may cost per month, in `currency`. |
| `currency` | string | no | The ISO 4217 code of `max_infra_per_month`, such as `EUR`. |
| `new_paid_service` | `ask` \| `allowed` \| `forbidden` | no | A new paid service: `ask` a person first (the default reading when unset), `allowed` within the budget, or `forbidden`. |
<!-- aidd:end -->

`project.defaults` holds the product defaults. Each is on unless `disabled` names it, with the reason as the value, such as `disabled: {dark_mode: a print-only report}`. [HOW-TO](HOW-TO.md#product-defaults-and-how-to-turn-one-off) says what each one builds, and how to turn one off.

<!-- aidd:gen fields:config-project-defaults -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `disabled` | mapping | no | The defaults turned off, each with the one line a reader accepts as the reason, such as "no user interface". Every default it does not name is on. |
<!-- aidd:end -->

`project.compliance` names what the product must be ready for, such as `targets: [soc2, gdpr]`. [ADOPTION](ADOPTION.md) says what compliance turns on.

<!-- aidd:gen fields:config-project-compliance -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `targets` | list of `soc2` \| `iso27001` \| `gdpr` \| `hipaa` \| `pci-dss` \| `fedramp` \| `cra` \| `other` | no | The frameworks and laws the product answers to: `soc2` (SOC 2 Trust Services Criteria), `iso27001` (ISO/IEC 27001:2022), `gdpr`, `hipaa`, `pci-dss`, `fedramp`, `cra` (the EU Cyber Resilience Act, Regulation (EU) 2024/2847), or `other` (name it in a project rule). Any target turns compliance on. `cra` leans on two controls most: EC-08 (scanning and an SBOM per release) and EC-18 (vulnerability handling). It needs a `support_period`, and `aidd doctor` checks the repository's `security.txt`. |
| `support_period` | mapping | no | How long the product gets security updates, which the CRA makes the manufacturer declare (Art. 13(8)). It is at least five years, unless people use the product for less time. `aidd validate` fails a config whose targets name `cra` without it, and warns once `ends` has passed. A parent that locks `project` keeps the later end. |
<!-- aidd:end -->

With the `cra` target, `support_period` declares how long the product gets security updates, such as `support_period: {ends: "2031-12"}`:

<!-- aidd:gen fields:config-project-compliance-support_period -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `ends` | string | yes | The last month of support, `YYYY-MM`: the month and year the buyer must see at the time of purchase (CRA Art. 13(19)). |
| `reason` | string | no | Why this length fits how long people use the product. Write one when the period is shorter than five years. |
<!-- aidd:end -->

`project.writing` lists the doc kinds written in ASD-STE100 Simplified Technical English, such as `ste_100: ["spec", "runbook"]`:

<!-- aidd:gen fields:config-project-writing -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `ste_100` | list of `acceptance` \| `adr` \| `agents` \| `analytics` \| `api` \| `architecture` \| `authz` \| `compliance` \| `contract` \| `data-map` \| `design-spec` \| `design-system` \| `epic` \| `exploration` \| `feedback` \| `glossary` \| `initiative` \| `migration` \| `postmortem` \| `proposal` \| `runbook` \| `slo` \| `spec` \| `tech-spec` \| `test-plan` \| `threat-model` \| `vendors` \| `vulnerability-policy` | no | The doc kinds written in ASD-STE100 Simplified Technical English: the objects (`spec`, `epic`, `initiative`, `proposal`, `runbook`, `postmortem`) and the kinds `aidd new` writes. Default empty: no kind opts in. |
<!-- aidd:end -->

Each `project.rules` entry:

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

Each `project.waivers` entry:

<!-- aidd:gen fields:config-project-waivers -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `rule` | string | yes | The id of the rule it waives. |
| `reason` | string | yes | Why the rule cannot hold for now. |
| `approved_by` | string | yes | The person who approved it; never an agent or a bot account. |
| `until` | string | yes | The last day it holds. |
<!-- aidd:end -->
