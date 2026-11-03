# Config fields

Read this file to maintain `.aidd/config.yaml` or to read evidence. Agents rarely need it, and edit the config only when a person asks. `aidd gen-docs` generates the tables from the schemas that come with the CLI.

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
| `profile` | `profile` | yes | The profile (schemas/profiles.json): its risk rules on top of the built-in ones, and the routes on which the agent asks for Spec approval. `team` asks on more routes than `solo`. |
| `extends` | list of mapping (`extends`) | no | Parent configs merged first, such as an org preset. A setting the child names replaces the parent's, except a key the parent locks, a library standard or company policy that binds, and a risk rule the parent marks `locked`. |
| `locks` | list of `project` \| `tests` \| `docs` \| `owners` \| `agents` \| `preview` \| `standards_policy` | no | Set by a parent config (an org preset): keys its children may not set. `project` binds the parent's `project`, which a child may then add to and tighten, never loosen. Children may add locks, never remove them. |
| `specs_dir` | string | no | Where Spec files live. Default `specs`. A folder inside the repository, never its top: the Specs folder is a role's write area. |
| `proposals_dir` | string | no | Where proposals live, one folder each. Default `proposals`. A folder inside the repository, never its top: a change only to it needs no Spec. Keep a client's proposals in a repository only people cleared for that client can read. |
| `docs` | mapping | no | Linked documents: where `aidd new` writes them, which ones `aidd validate` asks for, and how old they may grow. |
| `owners` | mapping | no | Who decides: the people agents ask, and the specialists a risky change names. |
| `agents` | mapping | no | How the agents work in this repository: which roles may suggest work nobody asked for, and the model and effort each role runs on. |
| `standards` | list of mapping | no | Standards: the team's own written rules and its copies of aidd's library standards (`aidd standard add`), each a Markdown document in the repository that agents read before a loop step, beside the standards their roles already apply. Each is opinionated (the default) or industry. `aidd doctor` checks each path, role, and `enforced_by` name, and each copy against the library. A child config adds entries; it cannot drop or redefine one a parent names. |
| `standards_policy` | mapping | no | A company's rules for library standards, usually in its org preset: `aidd standard add` follows them and `aidd doctor` reports a breach. Only opinionated ids: an industry standard is never excluded or replaced, only waived per project, with a reason and an expiry. A child config adds and tightens: it cannot drop a parent's entry, require what a parent excludes, or allow a stack the parent does not. |
| `tests` | list of mapping (`test_command`) | no | The repository suite, run on every change by `aidd test`. Empty means a Spec brings its own commands. |
| `preview` | mapping | no | The one-command local preview: no hosting, no cost. The verifier starts it from a clean checkout of the head and records screenshots, a trace or video, and API transcripts under `.aidd/evidence/preview/<head_sha>/`, for people. `aidd init` fills it only when the command is obvious (a Docker Compose file). |
| `project` | mapping | no | The project's constraints and rules, set by humans: a technology radar, the hosting, a budget, the team's own rules each with its why, and the waivers a person approved. Agents read them in Specify and Review; `aidd risk --paths` prints the rules that apply to the paths in question, must first. `aidd validate` checks them. A parent that lists `project` in `locks` binds its rules, its hold list, its budget, and its hosting: a child may add rules and raise a rule's level, never lower one, waive a locked rule, or spend more. |
| `risks` | mapping (`risks`) | no | This repository's risk rules over the built-in ones (schemas/risks.json): its own areas and actions, and rules that add to or replace the built-in ones. `aidd risk --list` shows the rules in force and where each comes from. |
<!-- aidd:end -->

### Config sub-tables

#### `owners`

The people an agent asks, and the specialists a risky change names. A person answers an ask; the list only says whom to ask first.

<!-- aidd:gen fields:config-owners -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `default_owner_team` | string | no | owner_team that `aidd new` writes into new objects. |
| `approvers` | list of string | no | The people an agent asks for a decision (`ask`), first to last: users, @org/team, or `email:you@example.com`. Empty or missing, the agent asks whoever directs it. Under `team`, the platform's review decides who may merge. |
| `specialists` | mapping | no | Specialist pools by name, such as `security`, `privacy`, `finance`, `compliance`, or `data`: the people an agent names when a change's risk dimension calls for one, so the right person reviews it. |
<!-- aidd:end -->

`tests` entries use the test command fields in `references/spec.md`. `extends` entries:

<!-- aidd:gen fields:config-extends -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `path` | string | no | Repo-relative path to a parent config: no leading / or ./, no .., backslashes, or wildcards. |
| `url` | string | no | HTTPS URL of a parent config. |
| `sha256` | string | no | Required with url. Pins the content. |
<!-- aidd:end -->

A parent config (an org preset) may list keys in `locks`, so its children cannot set them, and mark a risk rule `locked: true`, so a child keeps its level.

#### `risks`

The project's own areas, actions, and rules, on top of the built-in ones in `schemas/risks.json`. A config area or action with a built-in's id replaces it, and a rule with a built-in's selector replaces that rule. The rule shape, which rule wins, and an example: `references/risk.md`. After a change, `aidd upgrade --yes` writes the new `ask` commands into the harness's ask rules, and `aidd risk --list` shows the result.

#### `preview`

The one command that starts the app on this machine with seed data. The verifier runs it from a clean checkout of the head (a git worktree) and exercises each Acceptance item. It saves screenshots, a trace or video, and API transcripts under `.aidd/evidence/preview/<head-sha>/`, for people. Evidence is the exit codes only.

<!-- aidd:gen fields:config-preview -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `command` | list of string | yes | Starts the app on this machine with its seed data (the command loads them), from a clean checkout, such as ["docker", "compose", "up", "--build"]. The verifier runs it in a worktree of the exact head commit. |
| `url` | string | no | Where the running preview answers, such as http://localhost:3000: the address the verifier drives. |
<!-- aidd:end -->

#### `standards`

Standards are the team's own rules and its copies of library standards. Before a step, read each one listed for your role whose `when_changed` matches the change. Never edit a copy (an entry with `from_library`).

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

## Project constraints (`project`)

Humans set them. Agents read them before Specify and Review. A design fits `adopt` or `trial`. A `hold` item needs an ADR and a person's decision. A person approves a waiver, never an agent: ask, and record it with their name on their yes.

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
| `spec_phase` | boolean | no | True when `aidd test` ran in the Spec phase: every changed path was the Spec or a file it freezes, and a Task had yet to change anything, so failing green results were expected. |
| `partial` | boolean | no | True when `aidd test --changed` ran only the commands the working-tree diff selects. A local convenience between steps: partial evidence never stands for the whole suite. |
| `dirty_tree` | boolean | no | True when the tests ran in a tree that holds what the head commit does not: uncommitted changes, untracked files no `.gitignore` in the repository ignores, or files git is told not to look at. None of its results is evidence for the head commit. |
| `dirty_paths` | list of string | no | The first of those paths, sorted, for the person who commits or stashes them. |
<!-- aidd:end -->
