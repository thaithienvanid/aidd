# Config fields

Read this to maintain `.aidd/config.yaml` or read evidence (rule 1 of the skill: edit it only when a person asks). `aidd gen-docs` generates the tables from the CLI's schemas. The `risks` rules: `references/risk.md`.

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
| `profile` | `profile` | yes | The profile (schemas/profiles.json): its risk rules on top of the built-in ones, which set when the agent asks for Spec approval. `team` asks on more routes than `solo`. A lock freezes it; a child cannot raise it. |
| `extends` | list of mapping (`extends`) | no | Parent configs merged first, such as an org preset. A child changes only what it names: a mapping merges member by member and keeps every entry, a list of named things merges by name, and any other list or a value replaces. A preset locks what it must hold. |
| `locks` | list of `profile` \| `project` \| `tests` \| `docs` \| `owners` \| `agents` \| `limits` \| `preview` \| `standards_policy` \| `environments` \| string | no | Set by a parent config: what its children may not set. An item is a key or one member of it (`docs.disabled`). A lock freezes the value, except `project`, which only tightens. Children may add locks, never remove them. |
| `specs_dir` | string | no | Where Spec files live. Default `specs`. A folder inside the repository, never its top: the Specs folder is a role's write area. |
| `proposals_dir` | string | no | Where proposals live, one folder each. Default `proposals`. A folder inside the repository, never its top: a change only to it needs no Spec. Keep a client's proposals in a repository only its cleared people can read. |
| `docs` | mapping | no | Linked documents: where `aidd new` writes them, which ones `aidd validate` asks for, and how old they may grow. A lock freezes it. |
| `owners` | mapping | no | Who decides: the people agents ask, and the specialists a risky change names. A lock freezes it. |
| `agents` | mapping | no | How the agents work here: which roles may suggest work nobody asked for, and each role's model, effort, and turn limit. A lock freezes it. |
| `limits` | mapping | no | Named numbers that change what aidd decides or shows. A lock freezes it. |
| `delivery_teams` | mapping | no | The delivery teams sharing this repository, by name: each one set of the aidd-team roles, run in one harness by its approvers, over its own areas and the work whose `delivery_team` names it. `aidd status --delivery-team <name>` shows one team's work. Not the `team` profile. Unset: one team. |
| `standards` | list of mapping | no | Standards: the team's own written rules and its copies of aidd's library standards (`aidd standard add`), each a Markdown document that agents read before a loop step, beside their roles' standards. Each is an opinionated standard, one choice your team commits to; an industry standard lives only in the registry. `aidd doctor` checks each path, role, and `enforced_by` name, and each copy against the library. A child adds entries; it cannot drop or redefine one a parent names. |
| `standards_policy` | mapping | no | A company's rules for library standards, usually in its org preset: `aidd standard add` follows them and `aidd doctor` reports a breach. Only opinionated ids: an industry standard is never excluded or replaced, only waived per project, with a reason and an expiry. A child adds and tightens: it cannot drop a parent's entry, require what a parent excludes, or allow a stack the parent does not. A lock freezes it. |
| `tests` | list of mapping (`test_command`) | no | The repository suite, run on every change by `aidd test`. Empty means a Spec brings its own commands. A lock freezes it. |
| `preview` | mapping | no | The one-command local preview: no hosting, no cost. The verifier starts it from a clean checkout of the head and records screenshots, a trace or video, and API transcripts under `.aidd/evidence/preview/<head_sha>/`. `aidd init` fills it only when the command is obvious (a Docker Compose file). A lock freezes it. |
| `environments` | list of mapping (`environment`) | no | Where a push deploys: each environment has a name, branches, tags. A push to one is `deploy.run` there, which asks unless it says `shared: false`, and a rule's `environment` sets the level. Unset, a push asks as `git.push` and a delegated merge defers; `[]` says none deploys. A child adds or overrides one by name; a lock freezes the list. |
| `delegation` | mapping | no | A standing delegation: the asks the delegate answers for you, inside these limits, on a passing delegate check. Only the default branch's tip sets it, a parent can only narrow it, and a reserved action is always yours. Claude Code is the one harness that answers one in this version. |
| `mcp` | mapping | no | How aidd wires its own MCP server into each coding agent. |
| `project` | mapping | no | The project's constraints and rules, set by humans: a technology radar, the hosting, a budget, the team's own rules each with its why, and the waivers a person approved. Agents read them in Specify and Review; `aidd risk --paths` prints the rules that apply to the paths, must first. `aidd validate` checks them. A parent that locks `project` binds its rules, hold list, budget, and hosting. The lock tightens only: a child may add rules and raise a level, never lower one, waive a locked rule, or spend more. |
| `risks` | mapping (`risks`) | no | This repository's risk rules over the built-in ones (schemas/risks.json): its own areas and actions, and rules that add to or replace the built-in ones. `aidd risk --list` shows the rules in force and where each comes from. |
<!-- aidd:end -->

### Config sub-tables

#### `owners`

The list says whom to ask first; a person answers.

<!-- aidd:gen fields:config-owners -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `approvers` | list of string | no | The people an agent asks for a decision (`ask`), first to last: users, @org/team, or `email:you@example.com`. Empty or missing, the agent asks whoever directs it. Under `team`, the platform's review decides who may merge. |
| `specialists` | mapping | no | Specialist pools by name, such as `security`, `privacy`, `finance`, `compliance`, or `data`: the people an agent names when a change's risk dimension calls for one, so the right person reviews it. A pool that no risk dimension asks for, and that no area is named for (an expert pool takes its area's name), gets a warning from `aidd validate` and `aidd doctor`. |
<!-- aidd:end -->

`tests` entries use the test command fields in `references/spec-tests.md`. A test command's `related_tests` holds the command `aidd test --changed` runs for only the related tests, with `{changed_paths}` or `{base_commit}`, and `sees`, the files its runner traces; a full run and `--require-green` always run the full command.

`extends` entries:

<!-- aidd:gen fields:config-extends -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `path` | string | no | Repo-relative path to a parent config: no leading / or ./, no .., backslashes, or wildcards. |
| `url` | string | no | HTTPS URL of a parent config. |
| `sha256` | string | no | Required with url. Pins the content. |
<!-- aidd:end -->

#### `preview`

<!-- aidd:gen fields:config-preview -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `command` | list of string | yes | Starts the app on this machine with its seed data (the command loads them), from a clean checkout, such as ["docker", "compose", "up", "--build"]. The verifier runs it in a worktree of the exact head commit. |
| `url` | string | no | Where the running preview answers, such as http://localhost:3000: the address the verifier drives. |
<!-- aidd:end -->

#### `standards`

Read them before a step, as `references/loop.md` says.

<!-- aidd:gen fields:config-standards -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | Stable name, such as `api-errors`. |
| `path` | string | yes | The Markdown document that states the standard, repo-relative, such as `docs/standards/api-errors.md`. |
| `roles` | list of string | yes | aidd-team role keys that read it before their step, such as `developer` or `reviewer`, or `*` for every role. |
| `when_changed` | list of string | no | Load it only for a change that touches one of these paths. Omit to load it for every change. |
| `enforced_by` | list of string | no | Names of `tests` entries that check the rule, so `aidd test` checks it. Without one, the standard is guidance a reviewer checks. |
| `fills` | list of string | no | The open choices it answers, each `<pack or skill>:<choice>`, such as `ci-pipeline:linter` (`aidd standard list` names them). Optional for the team's own standard. `aidd doctor` warns about a choice no pack or skill declares, and about two copies of library standards that fill one choice for one ecosystem. |
| `from_library` | mapping | no | Written by `aidd standard add` for a copy of a library standard: never edit the copy. To change the rule, write your own standard and replace the library one in `standards_policy`. `aidd doctor` reports an edited copy and drift; `aidd upgrade` refreshes an unedited one. |
<!-- aidd:end -->

## Project constraints (`project`)

Humans set them. A design fits `adopt` or `trial`. A `hold` item needs an ADR and a person's decision. A person approves a waiver, never an agent: ask, and record it with their name on their yes.

<!-- aidd:gen fields:config-project-rules -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `id` | string | yes | Stable, unique name, such as `money-in-minor-units`; a waiver names it. |
| `requirement_level` | `must` \| `should` \| `may` | yes | How binding it is, in the BCP 14 sense (RFC 2119, RFC 8174): must, should (a reason to differ is written down), or may. |
| `statement` | string | yes | The rule, in one sentence. |
| `why` | string | yes | Why the rule exists, printed beside it. |
| `when_changed` | list of string | no | The paths it holds for. Omitted: every change. |
| `enforced_by` | list of string | no | `tests` names that check it. Without one, a reviewer does. |
| `source` | string | no | The ADR or document that decided it. |
| `owner` | string | yes | The person or team who answers for it. |
| `review_due` | string | no | When its owner reviews it again; `aidd validate` warns once it has passed. |
<!-- aidd:end -->

<!-- aidd:gen fields:config-project-waivers -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `rule` | string | yes | The id of the rule it waives, or of an industry standard. |
| `reason` | string | yes | Why the rule cannot hold for now. |
| `granted_by` | string | yes | Who granted it, in a Spec's `approved_by` form; never an agent or a bot. |
| `until` | string | yes | The last day it holds. |
<!-- aidd:end -->

## Evidence (`.aidd/evidence/evidence.json`)

<!-- aidd:gen fields:evidence -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `aidd_version` | string | yes | The aidd release this record conforms to; the method and the toolkit share one version. |
| `aidd_commit` | string | no | The aidd commit that ran the tests, from a checkout or a git install; a release has none. |
| `head_sha` | string | yes | The commit the green results ran on. |
| `base_sha` | string | yes | The merge base the red results ran on. |
| `runner` | mapping | no | Which CI run produced this file. |
| `results` | list of mapping | yes | One entry per command and red_green run. An empty list exits 1, unless the run is `partial` or `untested`. |
| `specs` | list of string | no | The Specs this run answered to, by path. `aidd status` shows the run beside each. |
| `untested` | boolean | no | True when no test command applies to the changed paths (all are limited by `when_changed`). Exit 0, but no proof. |
| `specs_not_run` | list of string | no | Open Specs whose scope the change touched without holding them, by path. Their tests did not run. |
| `revised_frozen` | list of mapping | no | Each Spec the change revises (a `revisions` entry the head wrote) whose frozen files it also changes, so the gate passed those changes with a note instead of stopping. A person reads the field, because the head wrote the entry, and approves each Spec again. |
| `emergency_subset` | boolean | no | True when a Spec the run answers to has the emergency route and the repository's `tests` ran as their `smoke` set alone, so a green `tests` check does not cover the rest of the suite. The base commit's config decides which commands are smoke. The route is the Spec's own text, which a head can write for a Spec new in it, so a person reads this field. |
| `require_green` | boolean | no | True for `aidd test --require-green`: no failing test is excused. |
| `before_implement` | boolean | no | True when a Spec before Implement held only its own files, so its failing run was expected. Each excused result says so. |
| `partial` | boolean | no | True when `aidd test --changed` ran only what the working-tree diff selects, so it never stands for the whole suite. |
| `no_red` | boolean | no | True for `aidd test --no-red`, which skips the red run. |
| `target_moved` | mapping | no | Set when the target changed what decides after the fork. The run used the fork's values. |
| `dirty_tree` | boolean | no | True when the tests ran in a tree that differs from the head commit (a dirty tree), so no result in it is evidence for that commit. |
| `dirty_paths` | list of string | no | The first of those paths, sorted, for the person who commits or stashes them. |
<!-- aidd:end -->
