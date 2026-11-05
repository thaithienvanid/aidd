# Config reference

This is the complete reference for `.aidd/config.yaml`: every top-level key, then every table, field by field. The tables are generated from `schemas/config.schema.json` and `schemas/risks.schema.json`, which are the source of truth. Check a config with `aidd validate .aidd/config.yaml`, and the whole wiring with `aidd doctor`.

The config is advice for your agents. It says who they ask, what the tests are, and which actions they ask about first. aidd enforces none of it: your agent's own ask rules, which `aidd init` writes, and your platform's branch protection are the hard stops.

A minimal config:

```yaml
aidd_version: "1.0.0"
profile: team
owners:
  approvers: ["@your-org/leads"]
tests:
  - name: unit
    command: [npm, test]
risks:
  rules:
    - {action: pr.open, level: allow}
```

## Contents

<!-- aidd:gen toc -->
- [Contents](#contents)
- [Top-level keys](#top-level-keys)
- [Parents, presets, and locks](#parents-presets-and-locks)
- [`risks`](#risks)
- [`owners`](#owners)
- [`agents`](#agents)
- [`delivery_teams`](#delivery_teams)
- [`standards`](#standards)
- [`standards_policy`](#standards_policy)
- [`docs`](#docs)
- [`extends`](#extends)
- [`tests`](#tests)
- [`preview`](#preview)
- [`delegation`](#delegation)
- [`mcp`](#mcp)
- [`project`](#project)
<!-- aidd:end -->

## Top-level keys

<!-- aidd:gen fields:config -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `aidd_version` | string | yes | The aidd release this record conforms to; the method and the toolkit share one version. |
| `profile` | `profile` | yes | The profile (schemas/profiles.json): its risk rules on top of the built-in ones, and the routes on which the agent asks for Spec approval. `team` asks on more routes than `solo`. |
| `extends` | list of mapping (`extends`) | no | Parent configs merged first, such as an org preset. A setting the child names replaces the parent's, except a key the parent locks, a library standard or company policy that binds, and a risk rule the parent marks `locked`. |
| `locks` | list of `project` \| `tests` \| `docs` \| `owners` \| `agents` \| `preview` \| `standards_policy` | no | Set by a parent config (an org preset): keys its children may not set. `project` binds the parent's `project`, which a child may then add to and tighten, never loosen. Children may add locks, never remove them. |
| `specs_dir` | string | no | Where Spec files live. Default `specs`. A folder inside the repository, never its top: the Specs folder is a role's write area. |
| `proposals_dir` | string | no | Where proposals live, one folder each. Default `proposals`. A folder inside the repository, never its top: a change only to it needs no Spec. Keep a client's proposals in a repository only people cleared for that client can read. |
| `docs` | mapping | no | Linked documents: where `aidd new` writes them, which ones `aidd validate` asks for, and how old they may grow. |
| `owners` | mapping | no | Who decides: the people agents ask, and the specialists a risky change names. |
| `agents` | mapping | no | How the agents work in this repository: which roles may suggest work nobody asked for, and the model and effort each role runs on. |
| `delivery_teams` | mapping | no | The delivery teams sharing this repository, by name: each one set of the aidd-team roles, run in one harness by its people, over its own areas or Intents. `aidd status --delivery-team <name>` shows one team's work. Not the `team` profile. Unset: one team. |
| `standards` | list of mapping | no | Standards: the team's own written rules and its copies of aidd's library standards (`aidd standard add`), each a Markdown document in the repository that agents read before a loop step, beside the standards their roles already apply. Each is opinionated (the default) or industry. `aidd doctor` checks each path, role, and `enforced_by` name, and each copy against the library. A child config adds entries; it cannot drop or redefine one a parent names. |
| `standards_policy` | mapping | no | A company's rules for library standards, usually in its org preset: `aidd standard add` follows them and `aidd doctor` reports a breach. Only opinionated ids: an industry standard is never excluded or replaced, only waived per project, with a reason and an expiry. A child config adds and tightens: it cannot drop a parent's entry, require what a parent excludes, or allow a stack the parent does not. |
| `tests` | list of mapping (`test_command`) | no | The repository suite, run on every change by `aidd test`. Empty means a Spec brings its own commands. |
| `preview` | mapping | no | The one-command local preview: no hosting, no cost. The verifier starts it from a clean checkout of the head and records screenshots, a trace or video, and API transcripts under `.aidd/evidence/preview/<head_sha>/`, for people. `aidd init` fills it only when the command is obvious (a Docker Compose file). |
| `environments` | list of mapping (`environment`) | no | Where a push deploys: each environment a name, with its branches and tags. A push to one is `deploy.run` to that environment, which asks, and a rule's `environment` changes its level. Unset: such a push asks as `git.push`. |
| `delegation` | mapping | no | A standing delegation: the asks the delegate answers for you, inside these limits, on a passing delegate check. Only the default branch's tip sets it, a parent can only narrow it, and a reserved action is always yours. Claude Code is the one harness that answers one in this version. |
| `mcp` | mapping | no | How aidd wires its own MCP server into each coding agent. |
| `project` | mapping | no | The project's constraints and rules, set by humans: a technology radar, the hosting, a budget, the team's own rules each with its why, and the waivers a person approved. Agents read them in Specify and Review; `aidd risk --paths` prints the rules that apply to the paths in question, must first. `aidd validate` checks them. A parent that lists `project` in `locks` binds its rules, its hold list, its budget, and its hosting. A child may add rules and raise a rule's level, but never lower one, waive a locked rule, or spend more. |
| `risks` | mapping (`risks`) | no | This repository's risk rules over the built-in ones (schemas/risks.json): its own areas and actions, and rules that add to or replace the built-in ones. `aidd risk --list` shows the rules in force and where each comes from. |
<!-- aidd:end -->

## Parents, presets, and locks

`extends` layers parent configs under this one. An org preset is the root parent of every repository config: you name it with `AIDD_ORG_PRESET`. When they merge:

- a setting the child names replaces the parent's, and a mapping merges key by key
- a parent's `locks` names keys its children may not set, such as `tests` or `owners`. With `locks: ["project"]`, a child adds rules to `project` and raises their level, but never lowers one, waives a locked rule, or spends more, as [`project`](#project) explains
- a child adds library standards and tightens `standards_policy`, but never drops or loosens what a parent sets
- in `risks`, areas and actions merge by id, and rules by their selector (action, area, branch, role, environment). A rule a parent marks `locked: true` keeps the parent's level, and `aidd doctor` says when a child's change was set aside
- a preset's own parents are fetched by URL only, never from the repository, and a URL parent should carry its `sha256`. With `AIDD_OFFLINE=1`, a URL parent is skipped with a warning

## `risks`

`risks` changes the risk rules for this repository: which actions an agent takes on its own (`allow`), which it takes and reports (`report`), and which it asks a person about first (`ask`). The built-in rules are in `schemas/risks.json`, and `aidd risk --list` shows the rules in force and where each comes from.

- `areas` adds or replaces a named set of paths, such as your billing code. An area may raise the route of a change that touches it.
- `actions` adds or replaces an action, named `resource.verb`, with the shell command patterns it matches.
- `rules` adds a rule, or replaces the built-in rule with the same action, area, branch, role, and environment. The most specific rule that matches wins, and between equals the higher level.

```yaml
risks:
  areas:
    billing: {paths: ["src/billing/**"], route: major}
  actions:
    cloud.resource.create: {description: Commands that create paid cloud resources, commands: ["terraform apply*"]}
  rules:
    - {action: code.edit, area: billing, level: ask}
    - {action: cloud.resource.create, level: ask}
    - {action: code.edit, area: dependencies, level: ask}
    - {action: pr.open, level: allow}
```

After a change, `aidd upgrade --yes` writes the ask rules again into each coding agent's own settings.

`environments` names where a push deploys. Each environment has a name and the branch and tag globs whose push deploys there. `aidd risk --command` reads such a push as `deploy.run` to that environment, which asks, so the question says "deploy to production". A rule with `environment` changes one environment's level. A glob with no wildcard names only that ref, so `dev` never covers `dev/login`.

```yaml
environments:
  - {name: production, branches: [prod], tags: ["v*"]}
  - {name: dev, branches: [dev]}
risks:
  rules:
    - {action: deploy.run, environment: dev, level: report}
```

The `risks` block:

<!-- aidd:gen fields:risks-risks -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `areas` | mapping (`areas`) | no |  |
| `actions` | mapping (`actions`) | no |  |
| `rules` | list of mapping (`rule`) | no |  |
<!-- aidd:end -->

Each area:

<!-- aidd:gen fields:risks-area -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `description` | string | no |  |
| `paths` | list of string | yes | Globs, repo-relative; `**` matches any number of folders. |
| `exclude` | list of string | no | Globs a match must not also match, such as `**/vendor/**`. |
| `route` | `minor` \| `normal` \| `major` | no | The least route a change that touches the area needs. |
| `dimensions` | list of `data` \| `security` \| `privacy` \| `financial` \| `compliance` \| `availability` \| `third_party` \| `cost` \| `performance` | no | The risk dimensions a change in the area has, which name its specialists. |
| `deploys_on_merge` | list of string | no | The area's paths a host deploys from when they change on the default branch, such as `vercel.json`: a delegated merge never covers them. Only the built-in `infra` area sets it. |
<!-- aidd:end -->

Each action:

<!-- aidd:gen fields:risks-action -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `description` | string | no |  |
| `irreversible` | boolean | no | `true` when a person cannot undo the action, such as a force-push, a deploy, or a message sent. `aidd risk --suggest` never suggests lowering its rule. Left out, the action can be undone. |
| `commands` | list of string | no | Shell command patterns: `*` matches any run of characters, and a pattern matches the whole command. |
| `api_endpoints` | list of string | no | `gh api` endpoint globs whose write is this action, read from the call's parsed arguments in any flag order, which `commands` globs cannot do. This reads `gh api` only: a `glab api` pattern stays in `commands`. In a glob, `*` is any run of characters, `/` included, and `?` is one whole path segment, up to the next `/` or space. It is not one character, as in a path glob, and an entry cannot name a literal `?`. aidd cuts the query string off the endpoint before matching. A glob matches the whole endpoint without its query, ignoring case, or the endpoint and the call's field values after a space (`*dispatches*deploy*`); a file given to `--input` shows as `--input file`. Begin it with the methods it applies to (`DELETE */git/refs/*`, `PATCH\|POST */git/refs*`) or with none for any write. A GET or HEAD with no field or input is a read. A GraphQL mutation, or a query aidd cannot read, is the endpoint `graphql#mutation`. `aidd risk --command` reads them as parsed arguments. A harness's ask rules do not use them: those ask before any `gh api` call that may write, whatever its endpoint, while `aidd risk --command` reads the call exactly. Redefining an action replaces the whole entry, as with `commands`. |
| `file_reads` | mapping | no | Reading one of `paths` is this action: a shell command whose program is a reader, or the harness's own file-read tool where it has one. `aidd risk --command` reads each word after the program as a path. The harness's ask rules get a read rule for each of `paths`, and never one for `exclude`. Claude Code's rules then carve back out, with a `Read(!...)` rule each, the `.env` templates (`.env.example`, `.sample`, `.template`, `.dist`) and every other exclude but the template suffixes and `*.pub`, such as source code. Redefining an action replaces the whole entry, as with `commands`. |
| `tools` | list of string | no | Harness tool names the action is, such as an MCP tool that sends email. |
| `examples` | list of string | no | What the action looks like where no pattern catches it: the agent judges these. |
<!-- aidd:end -->

Each rule:

<!-- aidd:gen fields:risks-rule -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `action` | string | yes | An action id, or a prefix that ends in `.*` (`git.*`), or `*` for every action. |
| `area` | string | no |  |
| `branch` | `own` \| `default` \| `shared` | no |  |
| `role` | string | no |  |
| `environment` | string | no | A name in the config's `environments`: the rule decides `deploy.run` to that environment, such as a push to its branch. |
| `level` | `level` | yes | allow: the agent acts. report: it acts, then says what it did. ask: it waits for the person's yes, then acts. |
| `locked` | boolean | no | In an `extends` parent such as an org preset: a child's rule with the same selector keeps this level. |
| `reason` | string | no | Why the rule exists, in one line, which `aidd risk` shows. |
<!-- aidd:end -->

The built-in areas:

<!-- aidd:gen risks:areas -->
| Area | What it holds | Raises the route to | Dimensions | Editing it | Paths, such as |
| --- | --- | --- | --- | --- | --- |
| `auth` | Who can sign in and what each person may do: authentication, authorization, roles, sessions, tokens. | major | security | ask | `**/auth/**`, `**/authn/**`, `**/authz/**`, and 45 more |
| `payments` | Money moves or prices change: checkout, billing, payouts, invoices. | major | financial | ask | `**/payments/**`, `**/payment/**`, `**/billing/**`, and 6 more |
| `personal_data` | Data about people: users, customers, accounts, profiles, contacts, patients. | major | privacy | ask | `**/users/**`, `**/user/**`, `**/profile/**`, and 52 more |
| `secrets` | Secrets, keys, certificates, and cryptography. | major | security | ask | `**/crypto/**`, `**/secrets/**`, `**/secrets.*`, and 17 more |
| `migrations` | Database schema changes and data migrations. | major | data | ask | `**/migrations/**`, `**/migration/**`, `**/migrate/**`, and 9 more |
| `module_boundaries` | The rules that keep modules apart: import contracts and architecture tests. | major | none | report | `**/boundaries-baseline.*`, `**/.dependency-cruiser.*`, `**/.importlinter`, and 6 more |
| `ci` | What builds, tests, and ships the code: CI pipelines, git hooks, and code owners. | normal | third_party | report | `.github/workflows/**`, `.github/CODEOWNERS`, `CODEOWNERS`, and 25 more |
| `infra` | Infrastructure as code and containers: what runs the service. | normal | availability | report | `**/*.tf`, `**/*.tfvars`, `**/terraform/**`, and 37 more |
| `dependencies` | Third-party code and build tools: manifests, lockfiles, and the bots that update them. | normal | third_party | report | `**/package.json`, `**/package-lock.json`, `**/pnpm-lock.yaml`, and 70 more |
| `agent_config` | What instructs or permits a coding agent: AGENTS.md, the skills, the harness settings, and aidd's config. | normal | none | report | `.aidd/**`, `**/AGENTS.md`, `**/AGENTS.override.md`, and 37 more |
| `risk_rules` | The files that set when an agent asks: aidd's config and the record of the ask rules it wrote, and each harness's own ask rules. An agent asks before it changes what makes it ask. | normal | none | ask | `.aidd/config.yaml`, `.aidd/harness-rules.json`, `.claude/settings.json`, and 8 more |
| `project_config` | How the project checks its code and draws its product: test, lint, and type settings, app manifests, the design system, standards, and module APIs. | normal | none | report | `**/jest.config.*`, `**/vitest.config.*`, `**/jest.setup.*`, and 65 more |
<!-- aidd:end -->

The built-in rules:

<!-- aidd:gen risks:rules -->
| Action | Area | Branch | Level |
| --- | --- | --- | --- |
| `code.edit` | any | any | **allow** |
| `code.edit` | auth | any | **ask** |
| `code.edit` | payments | any | **ask** |
| `code.edit` | personal_data | any | **ask** |
| `code.edit` | secrets | any | **ask** |
| `code.edit` | migrations | any | **ask** |
| `code.edit` | module_boundaries | any | **report** |
| `code.edit` | ci | any | **report** |
| `code.edit` | infra | any | **report** |
| `code.edit` | dependencies | any | **report** |
| `code.edit` | agent_config | any | **report** |
| `code.edit` | project_config | any | **report** |
| `code.edit` | risk_rules | any | **ask** |
| `git.commit` | any | any | **allow** |
| `git.push` | any | own | **allow** |
| `git.push` | any | default | **ask** |
| `git.push` | any | shared | **ask** |
| `git.push.force` | any | any | **ask** |
| `git.history.rewrite` | any | any | **ask** |
| `git.branch.delete` | any | any | **ask** |
| `git.tag.create` | any | any | **ask** |
| `git.merge` | any | any | **ask** |
| `git.merge` | any | own | **allow** |
| `pr.open` | any | any | **report** |
| `pr.merge` | any | any | **ask** |
| `workflow.run` | any | any | **report** |
| `dependency.add` | any | any | **report** |
| `network.listen` | any | any | **report** |
| `commit_status.post` | any | any | **ask** |
| `branch_protection.change` | any | any | **ask** |
| `repo.settings.change` | any | any | **ask** |
| `intent.agree` | any | any | **ask** |
| `spec.approve` | any | any | **ask** |
| `spec.revise` | any | any | **ask** |
| `deploy.run` | any | any | **ask** |
| `records.push` | any | any | **ask** |
| `release.publish` | any | any | **ask** |
| `migration.run` | any | any | **ask** |
| `migration.run.local` | any | any | **report** |
| `migration.rollback` | any | any | **ask** |
| `infra.apply` | any | any | **ask** |
| `data.delete` | any | any | **ask** |
| `data.production.access` | any | any | **ask** |
| `secret.use` | any | any | **ask** |
| `message.send` | any | any | **ask** |
| `money.spend` | any | any | **ask** |
<!-- aidd:end -->

## `owners`

`owners` names the people agents ask for a decision, and the specialists a risky change names. Under `team`, the platform's review decides who may merge.

<!-- aidd:gen fields:config-owners -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `default_owner_team` | string | no | owner_team that `aidd new` writes into new objects. |
| `approvers` | list of string | no | The people an agent asks for a decision (`ask`), first to last: users, @org/team, or `email:you@example.com`. Empty or missing, the agent asks whoever directs it. Under `team`, the platform's review decides who may merge. |
| `specialists` | mapping | no | Specialist pools by name, such as `security`, `privacy`, `finance`, `compliance`, or `data`: the people an agent names when a change's risk dimension calls for one, so the right person reviews it. |
<!-- aidd:end -->

## `agents`

`agents` sets how the agents work. `proactive_roles` names the roles that may suggest work nobody asked for, always as a draft Spec with `suggested_by: agent:<role>`, which stays a draft until a person records its `triage`. `models` and `effort` pick each role's model and effort, which `aidd init --team` and `aidd upgrade` write into each harness's own agent files.

<!-- aidd:gen fields:config-agents -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `proactive_roles` | list of string | no | Agent roles that may suggest work nobody asked for, always as a draft Spec with `suggested_by: agent:<role>` that stays a draft until a person records `triage` (`aidd validate` enforces it). Default: product-manager (which also drafts Specs from incoming issues), agile-coach, and sre. An empty list means agents only work when asked. |
| `models` | mapping | no | The model each aidd-team role runs on, as `provider/model` (`anthropic/claude-opus-5-5`) or `inherit` (the session's model). Key it by tier (`reasoning` or `execution`) or by role name. A role's own entry wins over its tier's, so one role, such as the verifier, can run on any model by name. A key that names no tier and no role selects nothing, and `aidd doctor` warns about it. `aidd init --team` and `aidd upgrade` write it into each harness's own agent model field. Claude Code takes only an `anthropic/` model or `inherit`, Codex only an `openai/` one, OpenCode the whole `provider/model`, and Kiro and Copilot the model name. Where a harness cannot run it, the generated file says so and the harness's default runs. `inherit` writes no model field outside Claude Code. Unset: the tier's default per harness. |
| `independent_review` | boolean | no | Opt in to review by a different provider: the verifier and the reviewer run on a provider other than the developer's, so a mistake one model family makes is checked by another. Set the three roles in `agents.models` as `provider/model`. `aidd init --team` says when `agents.models` does not give that, and the lead checks the developer's `Assisted-by` trailers against the reviewer's and verifier's reports. It advises and never blocks. Default: off. |
| `effort` | mapping | no | How hard each aidd-team role thinks, keyed by tier (`reasoning` or `execution`) or by role name, as `agents.models` is; a role's own entry wins over its tier's. `aidd init --team` and `aidd upgrade` write it into Claude Code's agent `effort:` field. Unset: reasoning `xhigh`, execution `high`. Claude Code's CLAUDE_CODE_EFFORT_LEVEL still overrides it. |
| `max_tokens_per_run` | integer | no | The spend cap of one `/aidd-team:autopilot` run, in tokens: the sum of each step's count from the harness, every token of its model calls, cache reads included, copied and never estimated. Once the sum passes it, autopilot stops and asks once whether to go on for one more cap's worth, so an unattended run never spends without a bound. Where the harness gives no count for each step, autopilot says so once at launch, writes each step's spend as `unknown`, and the cap can't stop that run. Default: 50000000, about five large role steps, because one step on a large Spec spends about 10000000, mostly in cache reads. |
<!-- aidd:end -->

```yaml
agents:
  proactive_roles: [product-manager, sre]  # default: product-manager, agile-coach, sre; [] means agents only work when asked
  models:
    reasoning: anthropic/claude-opus-5-5
    verifier: inherit
  max_tokens_per_run: 20000000  # autopilot stops and asks once a run spends more; default 50000000
```

## `delivery_teams`

`delivery_teams` lists the delivery teams that share one repository, by name. Each is one set of the aidd-team roles, run in one harness by its people. Its work is its Intents, their Specs, and the Specs whose Task scope touches its areas. `aidd status --delivery-team <name>` shows that work alone, and `/aidd-team:autopilot team:<name>` runs it, so each team's run keeps to its own work. Give the teams areas and Intents that don't overlap, because aidd doesn't check that. Without the key, the whole repository has one delivery team. The `team` profile is a different thing: it sets who approves.

<!-- aidd:gen fields:config-delivery_teams -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `people` | list of string | yes | The people who run the team and answer its asks: users, @org/team, or `email:you@example.com`. |
| `areas` | list of string | no | The areas the team works in, by name: a built-in area or one under `risks.areas`. A Spec whose Task scope touches one is the team's work. A name that is no area fails the config's load. |
| `intents` | list of string | no | The Intents the team owns, by id, such as `INTENT-3`, with the Specs under them. A team with only some slices names itself in their `owner_team`. |
| `harness` | string | no | The harness the team's roles run in, as `aidd init --harness` names it, such as `claude-code` or `opencode`. A name aidd does not know fails the config's load. Unset: the harness of whoever runs the team. |
| `models` | mapping (`models`) | no | The model each of the team's roles runs on, keyed as `agents.models` is. Unset: `agents.models`. |
<!-- aidd:end -->

A harness aidd does not know, or an area that neither the built-in rules nor `risks.areas` define, fails the config's load, so a team never sees less work by a typo.

```yaml
delivery_teams:
  payments:
    people: ["@alice", "@org/payments"]
    areas: [payments]
    harness: claude-code
    models: {reasoning: anthropic/claude-opus-5-5}
  web:
    people: ["@bob"]
    intents: [INTENT-3]
    harness: opencode
```

## `standards`

`standards` holds the team's own rules beside the ones each role already applies, and its copies of aidd's library standards. Each names a Markdown document, and the aidd-team roles that read it before their step. Optionally, it also names the paths that make it apply, and the `tests` that check it.

- `type` is `opinionated`, the default and the only value a project writes. An industry standard lives only in the registry, `schemas/industry-standards.json`, and a project only waives one, with a reason and an expiry.
- `fills` names the open choices it answers, such as `ci-pipeline:linter`. `aidd standard` lists the open choices.
- `aidd standard add <id>` and `aidd standard add --stack <name>` write a copy with its entry and its `tests`, as [STANDARDS.md](STANDARDS.md) explains.
- `aidd doctor` warns about a missing document, an unknown role, or an `enforced_by` naming no test. For a copy, it also warns about an edit and a newer library version.
- A child config adds standards; it cannot drop or redefine one a parent names.

<!-- aidd:gen fields:config-standards -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | Stable name, such as `api-errors`. |
| `path` | string | yes | The Markdown document that states the standard, repo-relative, such as `docs/standards/api-errors.md`. |
| `roles` | list of string | yes | aidd-team role keys that read it before their step, such as `developer` or `reviewer`, or `*` for every role. |
| `when_changed` | list of string | no | Load it only for a change that touches one of these paths. Omit to load it for every change. |
| `enforced_by` | list of string | no | Names of `tests` entries that check the rule, so `aidd test` checks it. Without one, the standard is guidance a reviewer checks. |
| `type` | `"opinionated"` | no | `opinionated`, the default and the only value here: a choice the team or company commits to, which a company can require, exclude, or replace. An industry standard (what the field agrees on) lives only in the registry, `schemas/industry-standards.json`; the packs apply it everywhere, and a project only waives it, with a reason and an expiry. |
| `fills` | list of string | no | The open choices it answers, each `<pack or skill>:<choice>`, such as `ci-pipeline:linter` (`aidd standard list` names them). Optional for the team's own standard. `aidd doctor` warns about a choice no pack or skill declares, and about two copies of library standards that fill one choice for one ecosystem. |
| `from_library` | mapping | no | Written by `aidd standard add` for a copy of a library standard: never edit the copy. To change the rule, write your own standard and replace the library one in `standards_policy`. `aidd doctor` reports an edited copy and drift; `aidd upgrade` refreshes an unedited one. |
<!-- aidd:end -->

```yaml
standards:
  - name: api-errors
    path: docs/standards/api-errors.md
    roles: [developer, reviewer]
    when_changed: ["src/api/**"]
    enforced_by: [contract]  # a `tests` entry that checks the rule
```

## `standards_policy`

`standards_policy` holds a company's rules for the library standards, usually in its org preset. `aidd standard add` follows them, and `aidd doctor` fails on a breach. A child config adds and tightens: it cannot drop a parent's entry, require what a parent excludes or replaces, or allow a stack the parent does not allow.

<!-- aidd:gen fields:config-standards_policy -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `require` | list of string | no | Library standards every project must carry; `aidd doctor` fails while one is missing. |
| `exclude` | list of string | no | Library standards no project may add. |
| `replace` | mapping | no | A library standard and the `standards` name of the company's own standard that takes its place, such as `python/mypy-typing: typing`. Projects cannot add the library one. |
| `allow_stacks` | list of string | no | The only stacks a project may add. Unset, any stack. |
<!-- aidd:end -->

```yaml
standards_policy:
  require: [python/uv-tooling]
  exclude: [python/mypy-typing]
  replace: {"python/ruff-lint-format": lint}  # the `standards` entry `lint` takes its place
  allow_stacks: [python-cli]
```

## `docs`

Where the project's official docs live, and which documents a Spec should link, which `aidd validate` asks for. A Spec's own documents go in its folder, `specs/<ID>/`. The matrix only warns, and nothing is asked of a minor change. A repository sets a kind to `warn`, the default, or `"off"`.

<!-- aidd:gen fields:config-docs -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `dir` | string | no | Where `aidd new <type> <topic> --spec <ID>` writes a linked document: `<dir>/adr/NNNN-<topic>.md` for an ADR, `<dir>/specs/<area or Spec id>/<type>-<topic>.<ext>` otherwise. Default `docs`. |
| `required` | mapping | no | Which types of linked document `aidd validate` asks a Spec for: each type `warn`, the default, or `off`. `warn` follows aidd's own rule for the type, the same in every repository, and `aidd validate` only warns: it never errors. A major Spec needs a tech-spec and a runbook, and its own Alternatives considered and Pre-mortem, or Rollout, count. It needs a threat-model when a risk dimension is security, privacy, or data. When compliance is on (`project.compliance` targets), a Task that touches an authentication, authorization, secrets, or cryptography path needs one, on normal too. An authz doc (the authorization matrix) is needed, on normal too, when a Task touches an authentication or authorization path (the `baseline:auth` paths) and either the risk names security or compliance is on. A major feat whose Tasks touch a user-facing path needs a design spec (`design-spec`, or `design.files`). A major Spec needs a test-plan only on a trigger: a compliance dimension or type, a device path, or `uat: true`. It needs a migration doc on a data dimension or type, or on an irreversible change. A compliance doc (its DPIA) is needed, on normal too, when a risk dimension is privacy, with the data map (`data-map`) suggested beside it. An analytics doc (a tracking plan) is needed, on normal too, when the Spec has a `hypothesis`. On normal, the design-spec, test-plan, and migration rules are suggestions that `aidd new spec` prints. Otherwise testing lives in the Spec's Acceptance and the tech spec's Test strategy. A child config cannot set `off` for a type its parent sets to `warn`. |
| `exemplars` | list of string | no | The project's best Specs, which a person names, such as `["specs/SPEC-12.md"]`. Whoever writes a Spec reads them first, for their shape and depth, never to copy them. `aidd validate` warns on a path that does not exist. aidd never chooses them. |
| `max_review_age_days` | integer | no | Days after a living doc's `reviewed_on` date before `aidd doctor` warns that it is stale. Default 180, about six months. The living docs are the architecture overview, the data map, the vendor register, the glossary, and every doc a Spec links with `frozen: false`, except a runbook, which has `tested_on`. `reviewed_on` is optional: a person sets it in the doc's `---` YAML front matter each time they review the doc. A doc nobody has reviewed lately describes a system that has moved on. |
| `max_runbook_age_days` | integer | no | Days after a runbook's `tested_on` date before `aidd doctor` warns that it is stale. Default 180. A runbook nobody has run lately is a guess at the moment it is needed. |
<!-- aidd:end -->

## `extends`

Each entry names one parent config, by repository path or by URL.

<!-- aidd:gen fields:config-extends -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `path` | string | no | Repo-relative path to a parent config: no leading / or ./, no .., backslashes, or wildcards. |
| `url` | string | no | HTTPS URL of a parent config. |
| `sha256` | string | no | Required with url. Pins the content. |
<!-- aidd:end -->

## `tests`

`tests` is the repository suite, which `aidd test` runs on every change beside the Spec's own tests. Empty means every Spec brings its own commands. Each entry is a test command; `new_behavior` belongs to a Spec's tests and is never set here.

aidd starts a command with no shell, so a command that needs an environment variable starts with `env`, as in `[env, PYTHONPATH=src, python3, -m, pytest]`. `aidd init` and `aidd validate` refuse a command whose first word is `NAME=value`, since that word would run as the program.

<!-- aidd:gen fields:test_command -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | Stable name used in evidence. |
| `command` | list of string | yes | Command vector, one argument per item. Never a shell string. |
| `new_behavior` | boolean | no | True when this command proves new or fixed behavior. It must fail on the base commit (red) and pass on head (green). |
| `timeout_seconds` | integer | no | Wall-clock limit. A timeout is a fail. Default 1800. |
| `smoke` | boolean | no | In the config's `tests`: part of the smoke set, the only repository commands an emergency change runs (with its own). When no command is marked, an emergency runs the whole suite. |
| `retries` | integer | no | How many more times a failing run on head is tried (default 0). Every attempt is kept in the evidence; a pass after a failure passes, marked flaky, and the flaky test is a finding. A red run on the base commit is never retried. |
| `when_changed` | list of string | no | Run and require this command only when a changed path matches. Omit to run it on every change. |
| `report` | string | no | A JUnit XML report this command writes, as a path in the repository (pytest `--junitxml`, Vitest `--reporter=junit`, jest-junit, gotestsum, cargo-nextest, PHPUnit `--log-junit`). `aidd test` reads it after each run and records the test cases that failed, so a red run can be told from "no tests found". A missing, stale, or unreadable report is a finding. The exit code stays the evidence. |
| `covers` | list of string | no | In a Spec: the Acceptance items this command proves, by id (`A1`, `A2`, ...). Optional; once any command declares it, `aidd validate` warns about an Acceptance item no command covers, and about an id the Acceptance section does not have. |
<!-- aidd:end -->

## `preview`

`preview` is the one command that starts the app on this machine with seed data. With it, the verifier can exercise each Acceptance item on the exact head, before anyone pays for an environment. `aidd init` writes it only when a Docker Compose file makes the command obvious.

<!-- aidd:gen fields:config-preview -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `command` | list of string | yes | Starts the app on this machine with its seed data (the command loads them), from a clean checkout, such as ["docker", "compose", "up", "--build"]. The verifier runs it in a worktree of the exact head commit. |
| `url` | string | no | Where the running preview answers, such as http://localhost:3000: the address the verifier drives. |
<!-- aidd:end -->

## `delegation`

`delegation` lets the `aidd-team:delegate` role answer some asks for you, inside the limits you set. Before each delegated ask, the delegate check reads the delegation from the default branch's tip, never from a working tree. It then checks the evidence again: the tests, the diff, and, where a remote exists, the platform's own check run and branch rules. The delegate may answer only on a passing check, and it can always defer to you. A reserved action is always yours, such as a deploy, a migration, a new dependency, or a secret. So is a change to what decides, such as this block. Under a delegation, `dependency.add` and `migration.run.local` rise to `ask`. Claude Code is the one harness that answers a delegated ask in this version; every other harness keeps its ask rules.

<!-- aidd:gen fields:config-delegation -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `to` | `"delegate"` | yes | The aidd-team role that answers your delegated asks: `delegate`. |
| `set_by` | string | yes | Who set the delegation, as `Name <email>`: the address you commit with, or your no-reply one. It goes into each delegated commit's `On-behalf-of` trailer, so it is public wherever the history is. |
| `decides` | any | yes | The asks the delegate answers: `all`, the reversible delegable asks your `aidd_version` knew, or a list of them (`spec.approve`, `git.push`, `git.merge`, `pr.merge`). |
| `reserved` | list of string | no | Actions you keep, on top of the built-in reserved list. |
| `default_branch` | string | no | The default branch, as you confirmed it to `aidd init`, such as `main`. With no remote, the check trusts a branch only when this field on that branch's own tip names it, so a ref an agent makes is never the default branch. |
| `default_branch_deploys` | boolean | no | Your answer to "Does merging to the default branch deploy anything?". Unset means unknown, so a delegated merge defers. |
| `review_by` | string | yes | After this date every ask defers, until you review the delegation. `aidd init` sets it 90 days ahead. |
| `digest` | `each_session` \| `each_answer` | no | When `aidd status` shows what was decided for you: once a session, or after each answer. |
<!-- aidd:end -->

## `mcp`

`mcp` says how aidd wires its own MCP server. By default, `aidd init` lets aidd's own MCP tools run with no prompt in Claude Code and Codex. Set `approve_own_tools: false` to keep them asking, then run `aidd upgrade --yes`. It takes out only the approvals aidd wrote, which `.aidd/mcp-approvals.json` lists.

<!-- aidd:gen fields:config-mcp -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `approve_own_tools` | boolean | no | Whether `aidd init` and `aidd upgrade` let aidd's own MCP tools run with no prompt: by name in Claude Code's `permissions.allow` and in Codex's aidd block. `false` keeps them asking: they write no approval, and take out the ones aidd wrote (`.aidd/mcp-approvals.json`). |
<!-- aidd:end -->

## `project`

The project's constraints and rules, set by humans and read by agents: a technology radar, the hosting, a budget, the team's own rules each with its why, and the waivers a person approved. `aidd validate` checks them.

Every product default is on until you turn it off. To turn one off, name it under `project.defaults.disabled` with the reason, such as `dark_mode: an internal tool with one theme`.

<!-- aidd:gen fields:config-project -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `repo` | string | no | The GitHub repository this config belongs to, as `owner/name`. `aidd init` writes it from `origin`. |
| `work` | `product` \| `client` | no | Whose work the repository holds: `product`, the team's own product (the default), or `client`, work for a client. With `client`, a goal starts with `/aidd-team:propose`, not `/aidd-team:plan`. |
| `stack` | mapping | no | A technology radar: what new work uses. A child config adds to each list. |
| `hosting` | string | no | Where the project runs, in a phrase, such as "one VPS in the EU". Agents design and deploy for it. |
| `dev_services` | mapping | no | The project's dev services, shared by every worktree on this machine. aidd gives each command it runs (`aidd test`, the teardown) AIDD_WORKTREE, a stable name per worktree, so the project names its database, bucket, and ports by it. |
| `budget` | mapping | no | What running the project may cost. The SRE picks the zero-cost option that fits first. |
| `rules` | list of mapping (`project_rule`) | no | The team's own rules. `aidd validate` fails on a repeated id and warns once a rule's `review_due` has passed. |
| `waivers` | list of mapping (`project_waiver`) | no | Time-boxed exceptions to a rule. `aidd validate` fails on a waiver of an unknown rule or one an agent or bot approved, warns 14 days before `until`, and fails once it has passed. |
| `defaults` | mapping | no | What every product gets unless a person turns it off: each default is on unless `disabled` names it, with the reason (`disabled: {dark_mode: a print-only report}`). Agents build them on the MVP's Day 0 and whenever a change touches the area, from `aidd-team:product-defaults`, which owns each one and its test. `aidd init` writes none of them, and in a repository it detects as a command-line tool or a library (no web or mobile interface) turns the interface defaults off with the reason "no user interface". A child's `disabled` replaces its parent's; when the parent locks `project`, the child may only drop keys (turn a default back on), never add one. |
| `compliance` | mapping | no | What the product must be ready for. Compliance is on when `targets` names a framework or law: `aidd risk --paths` names the `enterprise-controls` pack, `aidd validate` warns for a threat model and an authorization matrix on security and auth paths (`docs.required`), and `aidd init` writes the security-scanning workflow. The organizational work (policies, an ISMS, vendor reviews, training, a penetration test, the auditor) stays with people outside the team. `aidd validate` warns when a target that expects separation of duties (soc2, iso27001, pci-dss, fedramp, hipaa) meets the `solo` profile, which waives it. `aidd init` writes this table only when given `--compliance-target`. A parent that locks `project` keeps its targets: a child adds to them. |
| `writing` | mapping | no | How the project's documents are written. It only records an opt-in for the humans and agents who write them; no check or rule reads it. A parent that locks `project` keeps its types: a child adds to them. |
<!-- aidd:end -->

`project.stack`, the technology radar:

<!-- aidd:gen fields:config-project-stack -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `adopt` | list of string | no | The default for new work. |
| `trial` | list of string | no | In use on a trial basis: fine where the design says why. |
| `hold` | list of string | no | Not for new work without an ADR that records a person's decision. `aidd validate` warns when a Spec's Context or Design names one and the Spec links no ADR (a case-insensitive text match: a hint). |
<!-- aidd:end -->

`project.budget`:

<!-- aidd:gen fields:config-project-budget -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `max_infra_per_month` | number | no | The most the infrastructure may cost per month, in `currency`. |
| `currency` | string | no | The ISO 4217 code of `max_infra_per_month`, such as `EUR`. |
| `new_paid_service` | `ask` \| `allowed` \| `forbidden` | no | A new paid service: `ask` a person first (the default reading when unset), `allowed` within the budget, or `forbidden`. |
<!-- aidd:end -->

`project.defaults` holds the product defaults. Each is on unless `disabled` names it, with the reason as the value, such as `disabled: {dark_mode: a print-only report}`.

<!-- aidd:gen fields:config-project-defaults -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `disabled` | mapping | no | The defaults turned off, each with the one line a reader accepts as the reason, such as "no user interface". Every default it does not name is on. |
<!-- aidd:end -->

`project.compliance` names what the product must be ready for, such as `targets: [soc2, gdpr]`.

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

`project.writing` lists the doc types written in ASD-STE100 Simplified Technical English, such as `ste_100: ["spec", "runbook"]`:

<!-- aidd:gen fields:config-project-writing -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `ste_100` | list of `acceptance` \| `adr` \| `agents` \| `analytics` \| `api` \| `architecture` \| `authz` \| `compliance` \| `contract` \| `control-register` \| `data-map` \| `design-spec` \| `design-system` \| `exploration` \| `feedback` \| `glossary` \| `improvement-log` \| `intent` \| `metrics-dictionary` \| `migration` \| `postmortem` \| `product-brief` \| `proposal` \| `runbook` \| `service-card` \| `slo` \| `spec` \| `srs` \| `tech-spec` \| `test-plan` \| `threat-model` \| `vendors` \| `vulnerability-policy` | no | The doc types written in ASD-STE100 Simplified Technical English: the objects (`spec`, `intent`, `proposal`, `runbook`, `postmortem`) and the types `aidd new` writes. Default empty: no type opts in. |
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
| `approved_by` | string | yes | Who approved it, in a Spec's `approved_by` form; never an agent or a bot. |
| `until` | string | yes | The last day it holds. |
<!-- aidd:end -->
